"""The Telegram control bot: linking, owner-only control, cards with buttons,
Buy now / Exit / SL->cost, EXIT ALL with confirmation, BotFather auto-create."""

import json
from typing import Any

import httpx
import pytest
from httpx import AsyncClient

from app.container import Container
from tests.fakes import FakeTelegram
from tests.test_paper_trading import SIGNAL, ctr, price, push, setup, trades

pytestmark = pytest.mark.db

OWNER = 777
STRANGER = 999
TOKEN = "123456789:AAFakeTokenFakeTokenFakeTokenFakeTok"


class FakeBotServer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.updates: list[dict[str, Any]] = []
        self.next_id = 100

    def __call__(self, request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        body = json.loads(request.content) if request.content else {}
        self.calls.append((method, body))
        if TOKEN not in request.url.path:
            return httpx.Response(401, json={"ok": False, "description": "Unauthorized"})
        if method == "getMe":
            return httpx.Response(200, json={"ok": True, "result": {"username": "mos_test_bot"}})
        if method == "getUpdates":
            ups, self.updates = self.updates, []
            return httpx.Response(200, json={"ok": True, "result": ups})
        if method == "sendMessage":
            self.next_id += 1
            return httpx.Response(200, json={"ok": True, "result": {"message_id": self.next_id}})
        return httpx.Response(200, json={"ok": True, "result": True})

    def sent(self, method: str = "sendMessage") -> list[dict[str, Any]]:
        return [b for m, b in self.calls if m == method]

    def texts(self) -> list[str]:
        return [b["text"] for b in self.sent()] + [b["text"] for b in self.sent("editMessageText")]


def msg(chat: int, text: str) -> dict[str, Any]:
    return {"message": {"chat": {"id": chat}, "from": {"first_name": "Krish"}, "text": text}}


def press(chat: int, data: str) -> dict[str, Any]:
    return {
        "callback_query": {
            "id": "cb1",
            "data": data,
            "message": {"message_id": 5, "chat": {"id": chat}, "text": "card"},
        }
    }


async def linked_bot(c: AsyncClient) -> tuple[Container, FakeBotServer]:
    container = ctr(c)
    server = FakeBotServer()
    container.bot.transport = httpx.MockTransport(server)
    r = await c.put("/api/v1/bot/token", json={"token": TOKEN})
    assert r.status_code == 200, r.text
    assert r.json()["username"] == "mos_test_bot"
    link = (await c.post("/api/v1/bot/link")).json()
    assert link["url"] == f"https://t.me/mos_test_bot?start={link['code']}"
    await container.bot.handle_update(msg(STRANGER, "/start wrong-code"))
    assert (await c.get("/api/v1/bot")).json()["linked"] is False
    await container.bot.handle_update(msg(OWNER, f"/start {link['code']}"))
    status = (await c.get("/api/v1/bot")).json()
    assert status["linked"] is True
    assert status["owner_name"] == "Krish"
    return container, server


async def test_link_and_owner_only(db_client: AsyncClient) -> None:
    container, server = await linked_bot(db_client)
    assert any(b["chat_id"] == STRANGER and "private" in b["text"] for b in server.sent())
    welcome = next(b for b in server.sent() if b["chat_id"] == OWNER)
    assert welcome["reply_markup"]["keyboard"][0][1]["text"] == "🛑 EXIT ALL"
    assert server.sent("pinChatMessage")  # status pinned at the top
    # A stranger's button press is refused and nothing happens
    await container.bot.handle_update(press(STRANGER, "xall!"))
    answer = server.sent("answerCallbackQuery")[-1]
    assert answer["text"] == "Not allowed."
    assert (await db_client.get("/api/v1/settings")).json()["trading"]["kill_switch"] is False


async def test_waiting_trade_buy_now_and_exit_buttons(db_client: AsyncClient) -> None:
    c = db_client
    ctx = await setup(c)
    container, server = await linked_bot(c)
    await price(c, ctx["ce"]["id"], "110")
    await push(SIGNAL, "40")  # BUY ABOVE 120: waits
    [t] = await trades(c)
    card = server.sent()[-1]
    assert "Waiting for 120" in card["text"]
    buttons = [b["callback_data"] for row in card["reply_markup"]["inline_keyboard"] for b in row]
    assert buttons == [f"buy:{t['id']}", f"cx:{t['id']}"]

    await container.bot.handle_update(press(OWNER, f"buy:{t['id']}"))
    [t] = await trades(c)
    assert t["status"] == "open"
    assert any("Entered" in x for x in server.texts())
    edits = server.sent("editMessageText")
    assert any("In at 110.1" in e["text"] for e in edits)

    await container.bot.handle_update(press(OWNER, f"exa:{t['id']}"))
    [t] = await trades(c)
    assert t["status"] == "closed"
    assert any("Closed" in x for x in server.texts())


async def test_exit_all_needs_confirmation(db_client: AsyncClient) -> None:
    c = db_client
    ctx = await setup(c)
    container, server = await linked_bot(c)
    await price(c, ctx["ce"]["id"], "120")
    await push(SIGNAL, "41")
    await container.bot.handle_update(msg(OWNER, "🛑 EXIT ALL"))
    ask = server.sent()[-1]
    assert "Exit everything?" in ask["text"]
    assert (await trades(c))[0]["status"] == "open"  # nothing yet
    await container.bot.handle_update(press(OWNER, "xall!"))
    assert (await trades(c))[0]["status"] == "closed"
    assert (await c.get("/api/v1/settings")).json()["trading"]["kill_switch"] is True
    assert any("EXIT ALL" in x and "Kill switch ON" in x for x in server.texts())
    await container.bot.handle_update(press(OWNER, "ksoff"))
    assert (await c.get("/api/v1/settings")).json()["trading"]["kill_switch"] is False


async def test_paused_auto_asks_before_trading(db_client: AsyncClient) -> None:
    c = db_client
    ctx = await setup(c, auto=False)
    container, server = await linked_bot(c)
    await container.bot.handle_update(msg(OWNER, "▶️ Resume auto"))
    assert (await c.get("/api/v1/settings")).json()["trading"]["auto_execute"] is True
    await container.bot.handle_update(msg(OWNER, "⏸ Pause auto"))
    await price(c, ctx["ce"]["id"], "120")
    await push(SIGNAL, "42")
    assert await trades(c) == []
    card = server.sent()[-1]
    assert card["text"].startswith("🔔 Signal")
    trade_btn = card["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    assert trade_btn.startswith("trade:")
    await container.bot.handle_update(press(OWNER, trade_btn))
    [t] = await trades(c)
    assert t["status"] == "open"


async def test_create_bot_with_botfather_links_automatically(db_client: AsyncClient) -> None:
    c = db_client
    await setup(c)
    container = ctr(c)
    server = FakeBotServer()
    container.bot.transport = httpx.MockTransport(server)
    fake = FakeTelegram.instances[-1]

    async def deliver(peer: str, text: str) -> None:  # the user's /start reaches the bot
        server.updates.append({"update_id": 1, **msg(OWNER, text)})

    fake.on_send = deliver
    r = await c.post("/api/v1/bot/create")
    assert r.status_code == 200, r.text
    assert fake.created_bot is not None
    assert fake.created_bot[1].endswith("_bot")
    assert fake.sent[0][0] == "@mos_test_bot"
    assert r.json()["linked"] is True

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.container import Container
from tests.fakes import KITE_CSV, FakeLLM, FakeTelegram, msg

pytestmark = pytest.mark.db

CREDS = {
    "api_id": "123456",
    "api_hash": "0123456789abcdef0123456789abcdef",
    "phone": "+919876543210",
}

LLM_SIGNAL = {
    "is_signal": True,
    "reason": None,
    "side": "BUY",
    "symbol_text": "INFY",
    "underlying": "INFY",
    "instrument_type": "EQ",
    "strike": None,
    "expiry_text": None,
    "entry_low": "1500",
    "entry_high": "1500",
    "stop_loss": "1480",
    "targets": ["1550"],
    "confidence": 0.9,
}


def container_of(c: AsyncClient) -> Container:
    return c._transport.app.state.container  # type: ignore[attr-defined,no-any-return]


async def setup(c: AsyncClient, llm: FakeLLM | None = None) -> tuple[Container, str]:
    container = container_of(c)
    container.telegram.factory = FakeTelegram

    async def fetch(_: object) -> str:
        return KITE_CSV

    container.instruments.fetcher = fetch
    if llm is not None:
        container.llm.factory = lambda key, model: llm
        await c.put("/api/v1/integrations/llm", json={"api_key": "sk-ant-test-key-123"})
    await c.put("/api/v1/integrations/telegram", json=CREDS)
    await c.post("/api/v1/telegram/login/start")
    await c.post("/api/v1/telegram/login/code", json={"code": "12345"})
    src = (
        await c.post("/api/v1/telegram/channels", json={"channel_id": "-1001", "name": "Alpha"})
    ).json()
    return container, src["id"]


async def test_instrument_sync(db_client: AsyncClient) -> None:
    container = container_of(db_client)

    async def fetch(ex: object) -> str:
        return KITE_CSV

    container.instruments.fetcher = fetch
    r = await db_client.post("/api/v1/instruments/sync", json={"exchanges": ["NSE"]})
    assert r.status_code == 200
    assert r.json() == {"NSE": 8}  # NCO row skipped
    # idempotent upsert
    r = await db_client.post("/api/v1/instruments/sync", json={"exchanges": ["NSE"]})
    total = (await db_client.get("/api/v1/instruments", params={"limit": 1})).json()["total"]
    assert total == 8
    idx = (await db_client.get("/api/v1/instruments", params={"q": "NIFTY 50"})).json()["items"][0]
    assert idx["instrument_type"] == "INDEX"


async def test_live_message_becomes_validated_signal(db_client: AsyncClient) -> None:
    c = db_client
    _, source_id = await setup(c)
    await c.post("/api/v1/instruments/sync", json={"exchanges": ["NFO"]})
    fake = FakeTelegram.instances[-1]
    await fake.push("-1001", "50", "BUY NIFTY 24500 CE ABOVE 120 SL 100 TGT 140/160")

    sigs = (await c.get("/api/v1/signals")).json()["items"]
    assert len(sigs) == 1
    s = sigs[0]
    assert s["status"] == "validated"
    assert s["parser"] == "rule"
    assert s["symbol_text"] == "NIFTY 24500 CE"
    inst = (await c.get(f"/api/v1/instruments/{s['instrument_id']}")).json()
    assert (
        inst["tradingsymbol"] == "NIFTY2610824500CE"
    )  # nearest active expiry, not the expired one

    msgs = (await c.get(f"/api/v1/signal-sources/{source_id}/messages")).json()["items"]
    assert msgs[0]["status"] == "parsed"
    ev = (await c.get("/api/v1/events", params={"aggregate_id": s["id"]})).json()["items"][0]
    raw_ev = (await c.get("/api/v1/events", params={"event_type": "raw_message.received"})).json()[
        "items"
    ][0]
    assert ev["correlation_id"] == raw_ev["id"]  # causal chain preserved


async def test_unresolved_instrument_needs_review(db_client: AsyncClient) -> None:
    c = db_client
    await setup(c)
    await FakeTelegram.instances[-1].push("-1001", "51", "BUY RELIANCE 2450 SL 2420 TGT 2500")
    s = (await c.get("/api/v1/signals")).json()["items"][0]
    assert s["status"] == "new"
    assert "instrument not found" in s["notes"]

    await c.post("/api/v1/instruments/sync", json={"exchanges": ["NSE"]})
    inst = (await c.get("/api/v1/instruments", params={"q": "RELIANCE"})).json()["items"][0]
    r = await c.patch(
        f"/api/v1/signals/{s['id']}", json={"instrument_id": inst["id"], "status": "validated"}
    )
    assert r.status_code == 200
    assert r.json()["status"] == "validated"
    r = await c.patch(f"/api/v1/signals/{s['id']}", json={"status": "executed"})
    assert r.status_code == 422


async def test_noise_is_ignored_without_llm(db_client: AsyncClient) -> None:
    c = db_client
    _, source_id = await setup(c, llm=(llm := FakeLLM(LLM_SIGNAL)))
    await FakeTelegram.instances[-1].push("-1001", "52", "Good morning traders, market opens soon")
    assert (await c.get("/api/v1/signals")).json()["total"] == 0
    msgs = (await c.get(f"/api/v1/signal-sources/{source_id}/messages")).json()["items"]
    assert msgs[0]["status"] == "ignored"
    assert llm.calls == []  # no LLM spend on obvious noise


async def test_llm_fallback_for_unclear_message(db_client: AsyncClient) -> None:
    c = db_client
    await setup(c, llm=(llm := FakeLLM(LLM_SIGNAL)))
    await c.post("/api/v1/instruments/sync", json={"exchanges": ["NSE"]})
    await FakeTelegram.instances[-1].push(
        "-1001", "53", "Infosys looks ready, buy for 1550, protect 1480"
    )
    s = (await c.get("/api/v1/signals")).json()["items"][0]
    assert len(llm.calls) == 1
    assert s["parser"] == "llm"
    assert s["status"] == "validated"


async def test_llm_failure_falls_back_to_rules(db_client: AsyncClient) -> None:
    c = db_client
    await setup(c, llm=FakeLLM(fail=True))
    await FakeTelegram.instances[-1].push("-1001", "54", "BUY ITC 450 TGT 470")
    s = (await c.get("/api/v1/signals")).json()["items"][0]
    assert s["parser"] == "rule"
    assert s["status"] == "new"
    assert "llm down" in s["details"]["llm_error"]


async def test_catch_up_stores_missed_messages_and_expires_old_ones(db_client: AsyncClient) -> None:
    c = db_client
    container, _ = await setup(c, llm=(llm := FakeLLM(LLM_SIGNAL)))
    fake = FakeTelegram.instances[-1]
    old = msg("-1001", "60", "BUY INFY 1500 SL 1480 TGT 1550")
    old.sent_at = datetime.now(UTC) - timedelta(hours=5)
    fake.history["-1001"] = [old, msg("-1001", "61", "BUY ITC 450 SL 440 TGT 470")]
    assert await container.telegram.catch_up() == 2
    assert await container.telegram.catch_up() == 0  # dedupe
    by_symbol = {s["symbol_text"]: s for s in (await c.get("/api/v1/signals")).json()["items"]}
    assert by_symbol["INFY"]["status"] == "expired"
    assert by_symbol["ITC"]["status"] in ("new", "validated")
    assert llm.calls == []


async def test_parse_preview_and_reparse(db_client: AsyncClient) -> None:
    c = db_client
    _, source_id = await setup(c)
    r = await c.post(
        "/api/v1/signals/parse-preview", json={"text": "SELL INFY CMP 1500 SL 1530 TGT 1450"}
    )
    body = r.json()
    assert body["is_signal"] is True
    assert body["parser"] == "rule"
    assert body["side"] == "SELL"
    assert (await c.get("/api/v1/signals")).json()["total"] == 0  # preview stores nothing

    await FakeTelegram.instances[-1].push("-1001", "70", "BUY ITC 450 SL 440 TGT 470")
    raw = (await c.get(f"/api/v1/signal-sources/{source_id}/messages")).json()["items"][0]
    r = await c.post(f"/api/v1/messages/{raw['id']}/parse")
    assert r.json()["symbol_text"] == "ITC"

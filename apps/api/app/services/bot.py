"""The private MarketOS control bot on Telegram.

* Notifications: new signals, waiting trades (with ⚡ Buy now / ✖ Cancel),
  fills, TP hits, stops, closes, news and market-move alerts.
* Each trade has one "card" message that is edited in place as it changes,
  with buttons: Exit 1 lot · Exit all · SL → cost.
* A keyboard that stays at the bottom of the chat: 📊 Status · 🛑 EXIT ALL ·
  ⏸ Pause auto · ▶️ Resume auto. EXIT ALL asks for a second tap.
* A pinned status message at the top, refreshed every minute.

Only the linked owner chat is obeyed; everyone else is ignored. Linking uses a
one-time code (``/start <code>``) shown in Settings, or happens automatically
when the bot is created through the user's Telegram login.
"""

from __future__ import annotations

import asyncio
import contextlib
import html
import secrets as pysecrets
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.telegram.bot_api import BotApi, BotApiError
from app.core.errors import FeatureDisabledError, InvalidInputError, MarketOSError
from app.core.logging import get_logger
from app.events import Event, EventBus, EventType
from app.models import Instrument, Signal, TradePlan
from app.models.enums import ExitReason, SignalStatus, TradePlanStatus
from app.services.market_data import MarketDataService
from app.services.runtime import BotRuntime, RuntimeStore, TradingRuntime
from app.services.secrets import SecretName, SecretStore
from app.services.telegram import TelegramService
from app.services.trading import IST, SkipError, TradingEngine, legs_of

log = get_logger("marketos.bot")

LINK_TTL = timedelta(minutes=30)
B_STATUS, B_EXIT_ALL, B_PAUSE, B_RESUME = (
    "📊 Status",
    "🛑 EXIT ALL",
    "⏸ Pause auto",
    "▶️ Resume auto",
)
KEYBOARD = {
    "keyboard": [
        [{"text": B_STATUS}, {"text": B_EXIT_ALL}],
        [{"text": B_PAUSE}, {"text": B_RESUME}],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
}
COMMANDS = [
    ("status", "Positions and today's P&L"),
    ("exitall", "Exit everything and turn the kill switch on"),
    ("pause", "Stop auto-executing new signals"),
    ("resume", "Auto-execute new signals again"),
    ("killoff", "Turn the kill switch off"),
    ("help", "What this bot does"),
]
HELP = (
    "<b>MarketOS bot</b> (paper trading)\n"
    "• New trades arrive here. Waiting ones have <b>⚡ Buy now</b> and <b>✖ Cancel</b>; "
    "if you do nothing they execute automatically at the signal's price.\n"
    "• Open trades have <b>Exit 1 lot</b>, <b>Exit all</b> and <b>SL → cost</b>.\n"
    "• <b>🛑 EXIT ALL</b> exits everything and turns the kill switch on (asks first).\n"
    "• <b>⏸ Pause auto</b> stops auto-execution; signals then come with a Trade button."
)


def _money(v: Decimal | None) -> str:
    if v is None:
        return "—"
    sign = "-" if v < 0 else ""
    return f"{sign}₹{abs(v):,.2f}".replace(".00", "")


def _px(v: Decimal | None) -> str:
    if v is None:
        return "—"
    return f"{v.normalize():f}"


class BotStatus(BaseModel):
    configured: bool
    running: bool
    username: str | None
    linked: bool
    owner_name: str | None
    last_error: str | None
    notify: dict[str, bool]


class TelegramBotService:
    def __init__(
        self,
        secrets: SecretStore,
        runtime: RuntimeStore,
        bus: EventBus,
        session_factory: async_sessionmaker[AsyncSession],
        engine: TradingEngine,
        market: MarketDataService,
        telegram: TelegramService,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.secrets = secrets
        self.runtime = runtime
        self.bus = bus
        self.sf = session_factory
        self.engine = engine
        self.market = market
        self.telegram = telegram
        self.transport = transport
        self.api: BotApi | None = None
        self.username: str | None = None
        self.last_error: str | None = None
        self.polling = False
        self.spawn: Callable[[Awaitable[None], str], None] | None = None
        self.cards: dict[uuid.UUID, int] = {}  # trade plan -> message id
        self.signal_cards: dict[uuid.UUID, int] = {}
        self._offset: int | None = None
        self._lock = asyncio.Lock()

    # ---------------------------------------------------------------- setup
    async def reload(self) -> None:
        async with self._lock:
            if self.api is not None:
                await self.api.close()
            self.api, self.username = None, None
            token = await self.secrets.get(SecretName.TELEGRAM_BOT_TOKEN)
            if not token:
                return
            api = BotApi(token, self.transport)
            try:
                me = await api.get_me()
                await api.set_commands(COMMANDS)
            except MarketOSError as exc:
                self.last_error = exc.message
                await api.close()
                return
            self.api, self.username, self.last_error = api, me.get("username"), None
            await self.runtime.update(BotRuntime, username=self.username)

    async def save_token(self, token: str) -> BotStatus:
        token = token.strip()
        probe = BotApi(token, self.transport)
        try:
            await probe.get_me()
        finally:
            await probe.close()
        await self.secrets.put(SecretName.TELEGRAM_BOT_TOKEN, token)
        await self.runtime.update(BotRuntime, owner_chat_id=None, owner_name=None)
        await self.reload()
        return await self.status()

    async def clear(self) -> None:
        await self.secrets.delete(SecretName.TELEGRAM_BOT_TOKEN)
        await self.runtime.update(
            BotRuntime, owner_chat_id=None, owner_name=None, username=None, pinned_message_id=None
        )
        await self.reload()

    async def link_code(self) -> dict[str, str]:
        if self.api is None or not self.username:
            raise FeatureDisabledError("Save the bot token first.")
        code = pysecrets.token_urlsafe(9).replace("-", "x").replace("_", "y")
        await self.runtime.update(
            BotRuntime, link_code=code, link_expires_at=datetime.now(UTC) + LINK_TTL
        )
        return {"code": code, "url": f"https://t.me/{self.username}?start={code}"}

    async def create_with_botfather(self) -> BotStatus:
        """Create the bot from the user's own Telegram login, then link it
        automatically by sending ``/start <code>`` to it as the user."""
        if not self.telegram.authorized:
            raise FeatureDisabledError("Log in to Telegram first (Settings → Telegram).")
        suffix = pysecrets.token_hex(3)
        token = await self.telegram.adapter.create_bot("MarketOS", f"marketos_{suffix}_bot")
        await self.save_token(token)
        link = await self.link_code()
        await self.telegram.adapter.send_text(f"@{self.username}", f"/start {link['code']}")
        if self.polling is False and self.api is not None:
            # Not polling (tests / background services off): process the /start now.
            for u in await self.api.get_updates(self._offset, wait=0):
                await self.handle_update(u)
        return await self.status()

    async def status(self) -> BotStatus:
        rt = await self.runtime.get(BotRuntime)
        return BotStatus(
            configured=bool(await self.secrets.get(SecretName.TELEGRAM_BOT_TOKEN)),
            running=self.api is not None,
            username=self.username or rt.username,
            linked=rt.owner_chat_id is not None,
            owner_name=rt.owner_name,
            last_error=self.last_error,
            notify=rt.notify.model_dump(),
        )

    async def send_test(self) -> None:
        await self._send("✅ MarketOS bot is connected.", KEYBOARD)

    # ------------------------------------------------------------ polling
    async def run_forever(self) -> None:
        backoff = 2.0
        refresh_at = 0.0
        while True:
            if self.api is None:
                await asyncio.sleep(5)
                continue
            self.polling = True
            try:
                updates = await self.api.get_updates(self._offset, wait=25)
                for u in updates:
                    self._offset = int(u["update_id"]) + 1
                    try:
                        await self.handle_update(u)
                    except Exception:
                        log.exception("bot.update_failed")
                backoff = 2.0
                loop = asyncio.get_running_loop()
                if loop.time() >= refresh_at:
                    refresh_at = loop.time() + 60
                    await self.refresh_open_cards()
                    await self.refresh_pinned()
            except BotApiError as exc:
                self.last_error = exc.message
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
            except Exception:
                log.exception("bot.poll_failed")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def handle_update(self, u: dict[str, Any]) -> None:
        if u.get("update_id") is not None:
            self._offset = max(self._offset or 0, int(u["update_id"]) + 1)
        if "callback_query" in u:
            await self.on_callback(u["callback_query"])
        elif "message" in u:
            await self.on_message(u["message"])

    async def _owner(self) -> int | None:
        return (await self.runtime.get(BotRuntime)).owner_chat_id

    async def on_message(self, m: dict[str, Any]) -> None:
        if self.api is None:
            return
        chat = int(m["chat"]["id"])
        text = str(m.get("text") or "").strip()
        rt = await self.runtime.get(BotRuntime)
        if text.startswith("/start"):
            code = text.split(maxsplit=1)[1].strip() if " " in text else ""
            valid = (
                code
                and rt.link_code
                and pysecrets.compare_digest(code, rt.link_code)
                and rt.link_expires_at is not None
                and rt.link_expires_at > datetime.now(UTC)
            )
            if valid:
                frm = m.get("from") or {}
                name = " ".join(x for x in (frm.get("first_name"), frm.get("last_name")) if x)
                await self.runtime.update(
                    BotRuntime,
                    owner_chat_id=chat,
                    owner_name=name or frm.get("username"),
                    link_code=None,
                    link_expires_at=None,
                    pinned_message_id=None,
                )
                await self.api.send_message(chat, "✅ Linked to MarketOS.\n\n" + HELP, KEYBOARD)
                await self.bus.publish(
                    Event(type=EventType.BOT_LINKED, aggregate_type="bot", payload={"name": name})
                )
                await self.refresh_pinned()
                return
            if chat != rt.owner_chat_id:
                await self.api.send_message(
                    chat, "This is a private bot. Link it from MarketOS → Settings → Telegram bot."
                )
                return
        if chat != rt.owner_chat_id:
            return  # strangers are ignored
        cmd = text.lower().lstrip("/")
        if text == B_STATUS or cmd == "status":
            await self._send(await self.status_text(), KEYBOARD)
        elif text == B_EXIT_ALL or cmd == "exitall":
            await self._send(
                "🛑 <b>Exit everything?</b>\nCancels waiting trades, exits every open trade at "
                "market and turns the kill switch on.",
                {
                    "inline_keyboard": [
                        [
                            {"text": "Yes, EXIT ALL", "callback_data": "xall!"},
                            {"text": "No", "callback_data": "noop"},
                        ]
                    ]
                },
            )
        elif text == B_PAUSE or cmd == "pause":
            await self.runtime.update(TradingRuntime, auto_execute=False)
            await self._send("⏸ Auto-execution paused. New signals will ask you first.", KEYBOARD)
        elif text == B_RESUME or cmd == "resume":
            await self.runtime.update(TradingRuntime, auto_execute=True)
            await self._send("▶️ Auto-execution on.", KEYBOARD)
        elif cmd == "killoff":
            await self.engine.set_kill_switch(False, "telegram")
            await self._send("Kill switch off. New trades are allowed again.", KEYBOARD)
        else:
            await self._send(HELP, KEYBOARD)

    async def on_callback(self, cq: dict[str, Any]) -> None:
        if self.api is None:
            return
        msg = cq.get("message") or {}
        chat = int((msg.get("chat") or {}).get("id", 0))
        if chat != await self._owner():
            await self.api.answer_callback(cq["id"], "Not allowed.")
            return
        data = str(cq.get("data") or "")
        try:
            reply = await self._act(data, msg)
        except (MarketOSError, SkipError) as exc:
            reason = exc.message if isinstance(exc, MarketOSError) else exc.reason
            await self.api.answer_callback(cq["id"], f"❌ {reason}", alert=True)
            return
        await self.api.answer_callback(cq["id"], reply)

    async def _act(self, data: str, msg: dict[str, Any]) -> str:
        action, _, arg = data.partition(":")
        if action == "noop":
            await self._delete_buttons(msg)
            return "OK"
        if action == "xall!":
            r = await self.engine.exit_all("telegram")
            await self._delete_buttons(msg)
            return f"Exited {r['exited']}, cancelled {r['cancelled']}, flattened {r['flattened']}"
        if action == "ksoff":
            await self.engine.set_kill_switch(False, "telegram")
            return "Kill switch off"
        oid = uuid.UUID(arg.split(":")[0])
        if action == "buy":
            await self.engine.enter_now(oid)
            return "Buying at market"
        if action == "cx":
            await self.engine.exit_plan(oid, None)
            return "Cancelled"
        if action == "ex1":
            async with self.sf() as s:
                plan = await s.get(TradePlan, oid)
                inst = await s.get(Instrument, plan.instrument_id) if plan else None
            lot = inst.lot_size if inst else 1
            await self.engine.exit_plan(oid, lot)
            return f"Exiting {lot}"
        if action == "exa":
            await self.engine.exit_plan(oid, None, ExitReason.MANUAL)
            return "Exiting all of this trade"
        if action == "be":
            async with self.sf() as s:
                plan = await s.get(TradePlan, oid)
            if plan is None or plan.entry_price is None:
                raise InvalidInputError("The entry has not filled yet.")
            await self.engine.update_plan(oid, stop_loss=plan.entry_price, by="telegram")
            return "Stop-loss moved to cost"
        if action in ("trade", "approve"):
            await self._trade_signal(oid, approve=action == "approve")
            return "Trading it"
        if action == "reject":
            await self._set_signal_status(oid, SignalStatus.REJECTED)
            await self._delete_buttons(msg)
            return "Ignored"
        raise InvalidInputError("Unknown button.")

    async def _trade_signal(self, signal_id: uuid.UUID, approve: bool) -> None:
        if approve:
            async with self.sf() as s:
                sig = await s.get(Signal, signal_id)
                if sig is None:
                    raise InvalidInputError("Signal not found.")
                if sig.instrument_id is None or sig.stop_loss is None:
                    raise InvalidInputError("This signal needs fixing in MarketOS first.")
            await self._set_signal_status(signal_id, SignalStatus.VALIDATED)
        if (await self.runtime.get(TradingRuntime)).auto_execute:
            return  # the engine picks up the validated signal itself
        acct = await self.engine.ensure_paper_account()
        await self.engine.execute_signal(signal_id, acct.id)

    async def _set_signal_status(self, signal_id: uuid.UUID, status: SignalStatus) -> None:
        async with self.sf() as s:
            sig = await s.get(Signal, signal_id)
            if sig is None:
                raise InvalidInputError("Signal not found.")
            old = sig.status
            if old == status:
                return
            sig.status = status
            await s.commit()
        await self.bus.publish(
            Event(
                type=EventType.SIGNAL_STATUS_CHANGED,
                aggregate_type="signal",
                aggregate_id=signal_id,
                payload={"from": old, "to": status, "by": "telegram"},
            )
        )

    # -------------------------------------------------------- notifications
    async def on_event(self, e: Event) -> None:
        interesting = {
            EventType.TRADE_PLAN_CREATED,
            EventType.TRADE_PLAN_OPENED,
            EventType.TRADE_PLAN_REDUCED,
            EventType.TRADE_PLAN_UPDATED,
            EventType.TRADE_PLAN_CLOSED,
            EventType.SIGNAL_CREATED,
            EventType.SIGNAL_EXECUTION_SKIPPED,
            EventType.EXIT_ALL,
            EventType.KILL_SWITCH_CHANGED,
            EventType.NEWS_ALERT,
            EventType.MARKET_ALERT,
            EventType.REPLAY_FINISHED,
        }
        if e.type not in interesting or self.api is None:
            return
        if self.spawn is None:
            await self.notify(e)
        else:
            self.spawn(self.notify(e), f"bot:{e.type}")

    async def notify(self, e: Event) -> None:
        rt = await self.runtime.get(BotRuntime)
        if rt.owner_chat_id is None or self.api is None:
            return
        n = rt.notify
        p = e.payload
        try:
            if e.type == EventType.TRADE_PLAN_CREATED and e.aggregate_id and n.signals:
                await self.upsert_card(e.aggregate_id)
            elif (
                e.type in (EventType.TRADE_PLAN_OPENED, EventType.TRADE_PLAN_REDUCED)
                and e.aggregate_id
            ):
                await self.upsert_card(e.aggregate_id)
                if n.trades:
                    await self._send(await self._fill_text(e), silent=False)
            elif e.type == EventType.TRADE_PLAN_UPDATED and e.aggregate_id:
                await self.upsert_card(e.aggregate_id)
            elif e.type == EventType.TRADE_PLAN_CLOSED and e.aggregate_id:
                await self.upsert_card(e.aggregate_id)
                if n.trades and p.get("status") == TradePlanStatus.CLOSED:
                    await self._send(await self._closed_text(e.aggregate_id))
            elif e.type == EventType.SIGNAL_CREATED and e.aggregate_id and n.signals:
                await self.signal_card(e.aggregate_id)
            elif e.type == EventType.SIGNAL_EXECUTION_SKIPPED and n.skipped:
                await self._send(
                    f"⚪ Signal not taken: {html.escape(str(p.get('reason')))}", silent=True
                )
            elif e.type == EventType.EXIT_ALL:
                await self._send(
                    f"🛑 <b>EXIT ALL</b> ({html.escape(str(p.get('by')))}): "
                    f"exited {p.get('exited')}, cancelled {p.get('cancelled')}, "
                    f"flattened {p.get('flattened')}. Kill switch ON.",
                    {
                        "inline_keyboard": [
                            [{"text": "Turn kill switch off", "callback_data": "ksoff"}]
                        ]
                    },
                )
            elif (
                e.type == EventType.KILL_SWITCH_CHANGED
                and p.get("by") != "telegram"
                and not p.get("kill_switch")
            ):
                await self._send("Kill switch is off.", silent=True)
            elif e.type == EventType.NEWS_ALERT and n.news:
                await self._send(_news_text(p))
            elif e.type == EventType.MARKET_ALERT and n.market_moves:
                await self._send(f"📈 <b>Market move</b>: {html.escape(str(p.get('text')))}")
            elif e.type == EventType.REPLAY_FINISHED:
                await self._send(
                    f"🔁 Replay finished: {html.escape(str(p.get('summary')))}", silent=True
                )
        except MarketOSError as exc:
            self.last_error = exc.message
            log.warning("bot.notify_failed", error=exc.message, event_type=e.type)

    async def _send(
        self, text: str, markup: dict[str, Any] | None = None, silent: bool = False
    ) -> dict[str, Any] | None:
        owner = await self._owner()
        if owner is None or self.api is None:
            return None
        return await self.api.send_message(owner, text, markup, silent=silent)

    async def _delete_buttons(self, msg: dict[str, Any]) -> None:
        if self.api is None or not msg.get("message_id"):
            return
        with contextlib.suppress(MarketOSError):
            await self.api.edit_message(
                int(msg["chat"]["id"]), int(msg["message_id"]), str(msg.get("text") or "Done")
            )

    # ------------------------------------------------------------- cards
    async def _plan(self, plan_id: uuid.UUID) -> tuple[TradePlan, Instrument] | None:
        async with self.sf() as s:
            plan = await s.get(TradePlan, plan_id)
            inst = await s.get(Instrument, plan.instrument_id) if plan else None
        return (plan, inst) if plan and inst else None

    async def card(self, plan: TradePlan, inst: Instrument) -> tuple[str, dict[str, Any]]:
        ltp = (await self.market.ltp([inst])).get(inst.id)
        side = "🟢 BUY" if plan.side.value == "BUY" else "🔴 SELL"
        lots = plan.quantity // max(inst.lot_size, 1)
        legs = legs_of(plan)
        ladder = " · ".join(
            f"T{i + 1} {_px(leg.price)}x{leg.quantity}{' ✅' if leg.status == 'hit' else ''}"
            for i, leg in enumerate(legs)
            if leg.status != "cancelled"
        )
        lines = [f"{side} <b>{html.escape(inst.tradingsymbol)}</b> ({inst.exchange.value})"]
        if plan.status is TradePlanStatus.PENDING:
            lines.append(f"⏳ Waiting for {_px(plan.planned_entry)} · LTP {_px(ltp)}")
        elif plan.status is TradePlanStatus.OPEN:
            d = 1 if plan.side.value == "BUY" else -1
            unreal = (
                (ltp - plan.entry_price) * plan.open_quantity * d
                if ltp and plan.entry_price
                else None
            )
            lines.append(
                f"✅ In at {_px(plan.entry_price)} · LTP {_px(ltp)} · P&L {_money(unreal)}"
            )
        else:
            reason = (
                plan.exit_reason.value.replace("_", " ") if plan.exit_reason else plan.status.value
            )
            lines.append(
                f"🏁 {plan.status.value.title()} ({reason}) · P&L {_money(plan.realized_pnl)}"
            )
        trail = (plan.trailing or {}).get("mode", "none")
        lines.append(
            f"SL {_px(plan.stop_loss)}{' (trailing: ' + trail + ')' if trail != 'none' else ''}"
            + (f" · {ladder}" if ladder else "")
        )
        held = plan.open_quantity if plan.status is TradePlanStatus.OPEN else plan.quantity
        lines.append(f"Qty {held}/{plan.quantity} ({lots} lot{'s' if lots != 1 else ''})")
        pid = str(plan.id)
        if plan.status is TradePlanStatus.PENDING:
            kb = [
                [
                    {"text": "⚡ Buy now @ market", "callback_data": f"buy:{pid}"},
                    {"text": "✖ Cancel", "callback_data": f"cx:{pid}"},
                ]
            ]
        elif plan.status is TradePlanStatus.OPEN:
            row = [{"text": "Exit all", "callback_data": f"exa:{pid}"}]
            if plan.open_quantity > inst.lot_size:
                row.insert(0, {"text": "Exit 1 lot", "callback_data": f"ex1:{pid}"})
            kb = [row, [{"text": "SL → cost", "callback_data": f"be:{pid}"}]]
        else:
            kb = []
        return "\n".join(lines), {"inline_keyboard": kb}

    async def upsert_card(self, plan_id: uuid.UUID) -> None:
        found = await self._plan(plan_id)
        owner = await self._owner()
        if found is None or owner is None or self.api is None:
            return
        text, kb = await self.card(*found)
        mid = self.cards.get(plan_id)
        if mid is not None:
            try:
                await self.api.edit_message(owner, mid, text, kb)
                return
            except BotApiError:
                pass  # message deleted / too old: send a fresh card
        sent = await self.api.send_message(owner, text, kb)
        self.cards[plan_id] = int(sent["message_id"])

    async def refresh_open_cards(self) -> None:
        async with self.sf() as s:
            ids = list(
                await s.scalars(
                    select(TradePlan.id).where(
                        TradePlan.status.in_([TradePlanStatus.OPEN, TradePlanStatus.PENDING])
                    )
                )
            )
        for pid in ids:
            if pid in self.cards:
                await self.upsert_card(pid)

    async def signal_card(self, signal_id: uuid.UUID) -> None:
        async with self.sf() as s:
            sig = await s.get(Signal, signal_id)
            inst = await s.get(Instrument, sig.instrument_id) if sig and sig.instrument_id else None
        if sig is None:
            return
        auto = (await self.runtime.get(TradingRuntime)).auto_execute
        if sig.status is SignalStatus.VALIDATED and auto:
            return  # a trade card follows from the engine
        if sig.status not in (SignalStatus.VALIDATED, SignalStatus.NEW):
            return
        name = inst.tradingsymbol if inst else sig.symbol_text
        entry = (
            _px(sig.entry_low)
            if sig.entry_low == sig.entry_high
            else f"{_px(sig.entry_low)}-{_px(sig.entry_high)}"
        )
        tg = "/".join(str(t) for t in sig.targets) or "—"
        head = "🔔 Signal" if sig.status is SignalStatus.VALIDATED else "📝 Signal needs review"
        text = (
            f"{head}: <b>{sig.side.value} {html.escape(name)}</b>\n"
            f"Entry {entry} · SL {_px(sig.stop_loss)} · TGT {html.escape(tg)}"
        )
        if sig.notes and sig.status is SignalStatus.NEW:
            text += f"\n⚠️ {html.escape(sig.notes)}"
        sid = str(sig.id)
        btn = "▶ Trade it" if sig.status is SignalStatus.VALIDATED else "✅ Approve & trade"
        act = "trade" if sig.status is SignalStatus.VALIDATED else "approve"
        kb = {
            "inline_keyboard": [
                [
                    {"text": btn, "callback_data": f"{act}:{sid}"},
                    {"text": "✖ Ignore", "callback_data": f"reject:{sid}"},
                ]
            ]
        }
        sent = await self._send(text, kb)
        if sent:
            self.signal_cards[signal_id] = int(sent["message_id"])

    async def _fill_text(self, e: Event) -> str:
        p = e.payload
        sym = html.escape(str(p.get("symbol", "")))
        if e.type == EventType.TRADE_PLAN_OPENED:
            return f"✅ Entered <b>{sym}</b>: {p.get('quantity')} @ {p.get('entry_price')}"
        reason = str(p.get("reason"))
        icon = "🎯" if reason == ExitReason.TARGET else "↘️"
        what = "Target hit" if reason == ExitReason.TARGET else "Partial exit"
        return (
            f"{icon} {what} <b>{sym}</b>: {p.get('quantity')} @ {p.get('price')} "
            f"({p.get('open_quantity')} left)"
        )

    async def _closed_text(self, plan_id: uuid.UUID) -> str:
        found = await self._plan(plan_id)
        if found is None:
            return "Trade closed."
        plan, inst = found
        pnl = plan.realized_pnl or Decimal("0")
        icon = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"
        reason = plan.exit_reason.value.replace("_", " ") if plan.exit_reason else "closed"
        return f"{icon} Closed <b>{html.escape(inst.tradingsymbol)}</b> ({reason}): {_money(pnl)}"

    # -------------------------------------------------------------- status
    async def status_text(self) -> str:
        trading = await self.runtime.get(TradingRuntime)
        async with self.sf() as s:
            rows = list(
                (
                    await s.execute(
                        select(TradePlan, Instrument)
                        .join(Instrument, Instrument.id == TradePlan.instrument_id)
                        .where(
                            TradePlan.status.in_([TradePlanStatus.OPEN, TradePlanStatus.PENDING])
                        )
                        .order_by(TradePlan.created_at)
                    )
                ).all()
            )
            start = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0)
            today = await s.scalar(
                select(func.coalesce(func.sum(TradePlan.realized_pnl), 0)).where(
                    TradePlan.closed_at >= start
                )
            )
        prices = await self.market.ltp([i for _, i in rows]) if rows else {}
        lines = [
            f"<b>MarketOS</b> · {datetime.now(IST).strftime('%d %b %H:%M')} IST",
            f"Auto-execute: {'ON' if trading.auto_execute else 'paused'} · "
            f"Kill switch: {'🛑 ON' if trading.kill_switch else 'off'}",
            f"Realized today: {_money(Decimal(str(today or 0)))}",
        ]
        unreal_total = Decimal("0")
        for plan, inst in rows:
            ltp = prices.get(inst.id)
            if plan.status is TradePlanStatus.OPEN and ltp and plan.entry_price:
                d = 1 if plan.side.value == "BUY" else -1
                u = (ltp - plan.entry_price) * plan.open_quantity * d
                unreal_total += u
                lines.append(
                    f"• {html.escape(inst.tradingsymbol)} {plan.open_quantity} @ "
                    f"{_px(plan.entry_price)} → {_px(ltp)} ({_money(u)})"
                )
            else:
                lines.append(
                    f"• {html.escape(inst.tradingsymbol)} waiting for {_px(plan.planned_entry)}"
                )
        if not rows:
            lines.append("No open or waiting trades.")
        else:
            lines.append(f"Open P&L: {_money(unreal_total)}")
        return "\n".join(lines)

    async def refresh_pinned(self) -> None:
        rt = await self.runtime.get(BotRuntime)
        if rt.owner_chat_id is None or self.api is None:
            return
        text = "📌 " + await self.status_text()
        if rt.pinned_message_id:
            try:
                await self.api.edit_message(rt.owner_chat_id, rt.pinned_message_id, text)
                return
            except BotApiError:
                pass
        sent = await self.api.send_message(rt.owner_chat_id, text, silent=True)
        mid = int(sent["message_id"])
        with contextlib.suppress(BotApiError):
            await self.api.pin(rt.owner_chat_id, mid)
        await self.runtime.update(BotRuntime, pinned_message_id=mid)


def _news_text(p: dict[str, Any]) -> str:
    title = html.escape(str(p.get("title", "")))
    src = html.escape(str(p.get("source", "")))
    words = ", ".join(html.escape(str(w)) for w in p.get("matched", []))
    url = str(p.get("url") or "")
    link = f'\n<a href="{html.escape(url)}">Open</a>' if url.startswith("http") else ""
    return f"📰 <b>{title}</b>\n{src} · matched: {words}{link}"

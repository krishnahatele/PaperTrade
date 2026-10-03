"""Replay: re-run past Telegram signals against historical minute candles.

For each message in the chosen days and groups: parse it, find the contract as
of that day, fetch candles (Kite or Dhan), simulate entry/SL/targets/trailing
with the chosen risk settings, and store the outcome. Then build a report.

Isolated by design: writes only ``replay_runs`` / ``replay_trades``; never the
live signals, orders, positions or the paper account.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.broker.dhan import INDEX_SECURITY_IDS
from app.adapters.history.base import Candle, HistoryAdapter, HistoryUnavailableError
from app.adapters.telegram.base import InboundMessage
from app.core.errors import InvalidInputError, NotFoundError
from app.core.logging import get_logger
from app.events import Event, EventBus, EventType
from app.models import Instrument, RawMessage, ReplayRun, ReplayTrade, SignalSource
from app.models.enums import (
    Exchange,
    InstrumentType,
    ReplayOutcome,
    ReplayStatus,
    Segment,
    SignalSourceKind,
)
from app.parsing.models import ParsedSignal
from app.parsing.rules import parse_rules
from app.replay.report import build_report
from app.replay.simulator import SameCandle, SimSignal, simulate
from app.services.history import HistoryService
from app.services.instruments import InstrumentService, segment_of
from app.services.risk import AccountRiskSettings
from app.services.signal_pipeline import SignalPipeline
from app.services.telegram import TelegramService
from app.services.trading import TradingEngine

log = get_logger("marketos.replay")

# Used only when the instrument list has no contract of that index at all.
INDEX_LOT_FALLBACK = {
    "NIFTY": 75,
    "BANKNIFTY": 35,
    "FINNIFTY": 65,
    "MIDCPNIFTY": 140,
    "SENSEX": 20,
    "BANKEX": 30,
}


def _is_index_option(p: ParsedSignal) -> bool:
    return (
        p.instrument_type in (InstrumentType.CE, InstrumentType.PE)
        and p.strike is not None
        and str(p.underlying or "").upper() in INDEX_SECURITY_IDS
    )


IST = ZoneInfo("Asia/Kolkata")
MAX_DAYS = 31

# Intraday square-off (IST) per segment, like a broker's auto square-off.
SQUARE_OFF = {
    Segment.EQUITY: time(15, 20),
    Segment.FNO: time(15, 20),
    Segment.INDEX: time(15, 20),
    Segment.COMMODITY: time(23, 25),
    Segment.CURRENCY: time(16, 55),
}


class MessageOrigin(StrEnum):
    AUTO = "auto"  # Telegram history if logged in, else messages MarketOS stored
    TELEGRAM = "telegram"
    STORED = "stored"


class ReplayParams(BaseModel):
    name: str = Field(default="", max_length=128)
    date_from: date
    date_to: date
    source_ids: list[uuid.UUID] = Field(default_factory=list, description="Empty = all groups")
    messages: MessageOrigin = MessageOrigin.AUTO
    use_ai: bool = Field(default=False, description="AI for unclear messages (costs API calls)")
    settings: dict[str, Any] = Field(
        default_factory=dict, description="Overrides of the paper account's risk settings"
    )
    entry_window_minutes: int = Field(default=30, ge=1, le=24 * 60)
    square_off: bool = Field(default=True, description="Close intraday at the session end")
    same_candle: SameCandle = SameCandle.STOP_FIRST

    @model_validator(mode="after")
    def _range(self) -> ReplayParams:
        if self.date_to < self.date_from:
            raise ValueError("date_to is before date_from")
        if (self.date_to - self.date_from).days >= MAX_DAYS:
            raise ValueError(f"replay at most {MAX_DAYS} days at a time")
        if self.date_from > datetime.now(IST).date():
            raise ValueError("date_from is in the future")
        return self


class ReplayService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        bus: EventBus,
        telegram: TelegramService,
        pipeline: SignalPipeline,
        instruments: InstrumentService,
        history: HistoryService,
        engine: TradingEngine,
    ) -> None:
        self.sf = session_factory
        self.bus = bus
        self.telegram = telegram
        self.pipeline = pipeline
        self.instruments = instruments
        self.history = history
        self.engine = engine
        self.spawn: Callable[[Awaitable[None], str], None] | None = None
        self._cancel: set[uuid.UUID] = set()

    async def start(self, params: ReplayParams) -> ReplayRun:
        acct = await self.engine.ensure_paper_account()
        try:
            settings = AccountRiskSettings.model_validate({**acct.settings, **params.settings})
        except ValueError as exc:
            raise InvalidInputError(f"Invalid risk settings: {exc}") from exc
        name = params.name or (
            f"{params.date_from:%d %b %Y}"
            if params.date_to == params.date_from
            else f"{params.date_from:%d %b} to {params.date_to:%d %b %Y}"
        )
        run = ReplayRun(
            name=name,
            status=ReplayStatus.QUEUED,
            params={
                **params.model_dump(mode="json"),
                "resolved_settings": settings.model_dump(mode="json"),
            },
            progress={"stage": "queued"},
        )
        async with self.sf() as s:
            s.add(run)
            await s.commit()
            await s.refresh(run)
        if self.spawn is None:
            await self.run(run.id)
        else:
            self.spawn(self.run(run.id), f"replay:{run.id}")
        async with self.sf() as s:
            return await s.get(ReplayRun, run.id) or run

    def cancel(self, run_id: uuid.UUID) -> None:
        self._cancel.add(run_id)

    async def _progress(self, run_id: uuid.UUID, **fields: Any) -> None:
        async with self.sf() as s:
            run = await s.get(ReplayRun, run_id)
            if run is None:
                return
            for k, v in fields.items():
                if k == "progress":
                    run.progress = {**run.progress, **v}
                else:
                    setattr(run, k, v)
            await s.commit()

    # ------------------------------------------------------------------ run
    async def run(self, run_id: uuid.UUID) -> None:
        try:
            await self._run(run_id)
        except Exception as exc:
            log.exception("replay.failed", run=str(run_id))
            await self._progress(
                run_id,
                status=ReplayStatus.FAILED,
                error=getattr(exc, "message", None) or f"{type(exc).__name__}: {exc}",
                finished_at=datetime.now(UTC),
            )

    async def _run(self, run_id: uuid.UUID) -> None:
        async with self.sf() as s:
            run = await s.get(ReplayRun, run_id)
            if run is None:
                raise NotFoundError("Replay not found")
            raw_params = dict(run.params)
        params = ReplayParams.model_validate(raw_params)
        settings = AccountRiskSettings.model_validate(raw_params["resolved_settings"])
        await self._progress(
            run_id,
            status=ReplayStatus.RUNNING,
            started_at=datetime.now(UTC),
            progress={"stage": "collecting messages"},
        )
        start = datetime.combine(params.date_from, time(0, 0), IST).astimezone(UTC)
        end = datetime.combine(params.date_to + timedelta(days=1), time(0, 0), IST).astimezone(UTC)
        messages, origin = await self._messages(params, start, end)
        sources = await self.history.sources()
        await self._progress(
            run_id,
            progress={
                "stage": "simulating",
                "messages": len(messages),
                "done": 0,
                "origin": origin,
                "price_sources": [h.name for h in sources],
            },
        )
        candle_cache: dict[tuple[str, date, date], tuple[list[Candle], str] | str] = {}
        used: dict[str, int] = {}
        rows: list[ReplayTrade] = []
        for n, (src, m) in enumerate(messages, start=1):
            if run_id in self._cancel:
                self._cancel.discard(run_id)
                await self._progress(
                    run_id, status=ReplayStatus.CANCELLED, finished_at=datetime.now(UTC)
                )
                return
            row = await self._one(params, settings, src, m, sources, candle_cache, used, run_id)
            if row is not None:
                rows.append(row)
            if n % 10 == 0 or n == len(messages):
                await self._progress(run_id, progress={"done": n, "signals": len(rows)})
        async with self.sf() as s:
            s.add_all(rows)
            await s.commit()
            for r in rows:
                await s.refresh(r)
        report = build_report(
            rows,
            messages_scanned=len(messages),
            capital=settings.capital,
            sources_used=used,
        )
        report["message_origin"] = origin
        o = report["overall"]
        summary = (
            f"{o['traded']} trades from {o['signals']} signals, win rate {o['win_rate'] or '—'}%, "
            f"net ₹{o['net_pnl']}"
        )
        await self._progress(
            run_id,
            status=ReplayStatus.DONE,
            report=report,
            finished_at=datetime.now(UTC),
            progress={"stage": "done"},
        )
        await self.bus.publish(
            Event(
                type=EventType.REPLAY_FINISHED,
                aggregate_type="replay",
                aggregate_id=run_id,
                payload={"summary": summary},
            )
        )

    async def _messages(
        self, params: ReplayParams, start: datetime, end: datetime
    ) -> tuple[list[tuple[SignalSource, InboundMessage]], str]:
        async with self.sf() as s:
            q = select(SignalSource).where(SignalSource.kind == SignalSourceKind.TELEGRAM)
            if params.source_ids:
                q = q.where(SignalSource.id.in_(params.source_ids))
            sources = list(await s.scalars(q.order_by(SignalSource.name)))
        if not sources:
            raise InvalidInputError("No Telegram groups to replay. Add sources first.")
        use_tg = params.messages is MessageOrigin.TELEGRAM or (
            params.messages is MessageOrigin.AUTO and self.telegram.authorized
        )
        if params.messages is MessageOrigin.TELEGRAM and not self.telegram.authorized:
            raise InvalidInputError("Log in to Telegram to replay its history.")
        out: list[tuple[SignalSource, InboundMessage]] = []
        if use_tg:
            for src in sources:
                if not src.external_id:
                    continue
                msgs = await self.telegram.adapter.fetch_between(src.external_id, start, end)
                out.extend((src, m) for m in msgs)
            origin = "telegram"
        else:
            async with self.sf() as s:
                rows = await s.scalars(
                    select(RawMessage).where(
                        RawMessage.source_id.in_([x.id for x in sources]),
                        RawMessage.received_at >= start,
                        RawMessage.received_at < end,
                    )
                )
                by_id = {x.id: x for x in sources}
                for r in rows:
                    out.append(
                        (
                            by_id[r.source_id],
                            InboundMessage(
                                channel_id=by_id[r.source_id].external_id or "",
                                message_id=r.external_message_id,
                                text=r.content,
                                sent_at=r.received_at,
                            ),
                        )
                    )
            origin = "stored"
        out.sort(key=lambda x: x[1].sent_at)
        return out, origin

    async def _expired_index_option(
        self, p: ParsedSignal, sources: list[HistoryAdapter]
    ) -> Instrument | None:
        """An index option that isn't in the instrument list (usually a weekly that
        expired before the last sync). With Dhan as a price source we can still
        replay it from Dhan's expired-options data, using the strike from the message
        and the nearest expiry of that day. Not saved to the database."""
        if not _is_index_option(p) or not any(h.name == "dhan" for h in sources):
            return None
        und = str(p.underlying).upper()
        async with self.sf() as s:
            lot = await s.scalar(
                select(Instrument.lot_size)
                .where(
                    Instrument.name == und,
                    Instrument.instrument_type.in_([InstrumentType.CE, InstrumentType.PE]),
                )
                .order_by(Instrument.expiry.desc())
                .limit(1)
            )
        typ = p.instrument_type or InstrumentType.CE
        return Instrument(
            id=uuid.uuid4(),
            exchange=Exchange.BFO if und in ("SENSEX", "BANKEX") else Exchange.NFO,
            tradingsymbol=f"{und} {p.strike:f} {typ.value}"[:64],
            name=und,
            instrument_type=typ,
            strike=p.strike,
            expiry=None,
            lot_size=lot or INDEX_LOT_FALLBACK.get(und, 1),
            tick_size=Decimal("0.05"),
            broker_refs={},
        )

    async def _parse(self, params: ReplayParams, text: str) -> tuple[ParsedSignal, str]:
        if params.use_ai:
            outcome = await self.pipeline.parse_text(text, allow_llm=True)
            return outcome.parsed, (outcome.parser.value if outcome.parser else "rule")
        return parse_rules(text), "rule"

    async def _one(
        self,
        params: ReplayParams,
        settings: AccountRiskSettings,
        src: SignalSource,
        m: InboundMessage,
        sources: list[HistoryAdapter],
        cache: dict[tuple[str, date, date], tuple[list[Candle], str] | str],
        used: dict[str, int],
        run_id: uuid.UUID,
    ) -> ReplayTrade | None:
        p, parser = await self._parse(params, m.text)
        if not p.is_signal or p.side is None:
            return None
        row = ReplayTrade(
            run_id=run_id,
            source_id=src.id,
            source_name=src.name,
            message_id=m.message_id,
            message_text=m.text[:4000],
            message_at=m.sent_at,
            side=p.side,
            outcome=ReplayOutcome.INCOMPLETE,
            signal={
                "symbol_text": p.symbol_text,
                "underlying": p.underlying,
                "entry_low": str(p.entry_low) if p.entry_low is not None else None,
                "entry_high": str(p.entry_high) if p.entry_high is not None else None,
                "stop_loss": str(p.stop_loss) if p.stop_loss is not None else None,
                "targets": [str(t) for t in p.targets],
                "parser": parser,
                "confidence": str(p.confidence),
            },
        )
        day = m.sent_at.astimezone(IST).date()
        inst = await self.instruments.resolve(p, as_of=day)
        virtual = False
        if inst is None:
            inst = await self._expired_index_option(p, sources)
            virtual = inst is not None
        if inst is None:
            row.outcome = ReplayOutcome.UNRESOLVED
            row.tradingsymbol = (p.symbol_text or "?")[:64]
            why = await self.instruments.explain_unresolved(p, day)
            if _is_index_option(p) and not any(h.name == "dhan" for h in sources):
                why += "; connect Dhan (Data API) to replay expired index options"
            row.notes = why
            return row
        seg = segment_of(inst)
        row.tradingsymbol, row.segment = inst.tradingsymbol, seg.value
        row.instrument_id = None if virtual else inst.id
        if p.stop_loss is None:
            row.notes = "no stop-loss in the message"
            return row
        last = day if params.square_off else params.date_to
        key = (f"{inst.exchange.value}:{inst.tradingsymbol}", day, last)
        if key not in cache:
            try:
                cache[key] = await self.history.candles(inst, day, last, sources)
            except HistoryUnavailableError as exc:
                cache[key] = exc.message
        got = cache[key]
        if isinstance(got, str):
            row.outcome = ReplayOutcome.NO_DATA
            row.notes = got[:500]
            return row
        candles, src_name = got
        used[src_name] = used.get(src_name, 0) + 1
        sq = (
            datetime.combine(day, SQUARE_OFF.get(seg, time(15, 20)), IST).astimezone(UTC)
            if params.square_off
            else None
        )
        res = simulate(
            SimSignal(
                side=p.side,
                entry_low=p.entry_low,
                entry_high=p.entry_high,
                stop_loss=p.stop_loss,
                targets=list(p.targets),
                message_at=m.sent_at,
            ),
            candles,
            settings,
            inst.lot_size,
            inst.tick_size,
            timedelta(minutes=params.entry_window_minutes),
            sq,
            params.same_candle,
        )
        row.quantity = res.quantity or None
        if not res.entered:
            row.outcome = ReplayOutcome.ENTRY_NOT_HIT
            row.notes = res.note
            return row
        row.entry_price, row.entry_at = res.entry_price, res.entry_at
        row.exit_price, row.exit_at, row.exit_reason = res.exit_price, res.exit_at, res.exit_reason
        row.targets_hit = res.targets_hit
        row.gross_pnl, row.charges, row.net_pnl = res.gross, res.charges, res.net
        row.r_multiple, row.mfe, row.mae = res.r_multiple, res.mfe, res.mae
        row.legs = [leg.model_dump(mode="json") for leg in res.legs]
        net = res.net
        row.outcome = (
            ReplayOutcome.WIN
            if net > 0
            else ReplayOutcome.LOSS
            if net < 0
            else ReplayOutcome.BREAKEVEN
        )
        return row

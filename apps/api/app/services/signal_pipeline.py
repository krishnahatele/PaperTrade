"""Turns raw messages into signals: parse (rules, then LLM), resolve, validate, store."""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.events import Event, EventBus, EventType
from app.models import RawMessage, Signal
from app.models.enums import RawMessageStatus, SignalParser, SignalStatus
from app.parsing.llm import parse_llm
from app.parsing.models import ParsedSignal
from app.parsing.rules import parse_rules
from app.services.instruments import InstrumentService
from app.services.llm import LLMService
from app.services.runtime import ParserMode, ParsingRuntime, RuntimeStore, TradingRuntime

log = get_logger("marketos.signals")

# Rules results at or above this confidence are trusted without calling the LLM.
RULES_ACCEPT = 0.8
# Only spend LLM calls on messages that look like they could be trade calls.
_LOOKS_LIKE_SIGNAL = re.compile(
    r"\b(BUY|SELL|LONG|SHORT|CE|PE|CALL|PUT|FUT|SL|STOP\s*LOSS|TGT|TARGET)\b", re.I
)


class ParseOutcome(BaseModel):
    parser: SignalParser | None
    parsed: ParsedSignal
    llm_error: str | None = None


class SignalPipeline:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        bus: EventBus,
        runtime: RuntimeStore,
        llm: LLMService,
        instruments: InstrumentService,
        spawn: Callable[[Awaitable[None], str], None] | None = None,
    ) -> None:
        self.sf = session_factory
        self.bus = bus
        self.runtime = runtime
        self.llm = llm
        self.instruments = instruments
        self.spawn = spawn  # None => process inline (tests)
        self._llm_slots = asyncio.Semaphore(2)

    async def on_raw_message(self, event: Event) -> None:
        if event.aggregate_id is None:
            return
        raw_id = event.aggregate_id

        async def run() -> None:
            await self.process(raw_id, cause=event)

        if self.spawn is None:
            await run()
        else:
            self.spawn(run(), f"parse:{raw_id}")

    async def parse_text(
        self, text: str, *, allow_llm: bool = True, force_llm: bool = False
    ) -> ParseOutcome:
        parsing = await self.runtime.get(ParsingRuntime)
        rules = parse_rules(text)
        llm_ok = allow_llm and self.llm.configured and parsing.mode is not ParserMode.RULES_ONLY
        if force_llm and self.llm.configured:
            llm_ok = True
        use_llm_first = llm_ok and (force_llm or parsing.mode is ParserMode.LLM_ONLY)
        rules_good = rules.is_signal and float(rules.confidence) >= RULES_ACCEPT
        if not use_llm_first and (rules_good or not llm_ok or not _LOOKS_LIKE_SIGNAL.search(text)):
            return ParseOutcome(parser=SignalParser.RULE if rules.is_signal else None, parsed=rules)
        try:
            async with self._llm_slots:
                parsed = await parse_llm(self.llm.adapter, text)
        except Exception as exc:
            msg = getattr(exc, "message", None) or f"{type(exc).__name__}: {exc}"
            log.warning("signals.llm_failed", error=msg)
            return ParseOutcome(
                parser=SignalParser.RULE if rules.is_signal else None, parsed=rules, llm_error=msg
            )
        # Prefer whichever reading is more confident.
        if not force_llm and rules.is_signal and rules.confidence >= parsed.confidence:
            return ParseOutcome(parser=SignalParser.RULE, parsed=rules)
        return ParseOutcome(parser=SignalParser.LLM if parsed.is_signal else None, parsed=parsed)

    async def process(self, raw_message_id: uuid.UUID, cause: Event | None = None) -> Signal | None:
        async with self.sf() as s:
            raw = await s.get(RawMessage, raw_message_id)
            if raw is None:
                raise NotFoundError(f"RawMessage {raw_message_id} not found")
            text, source_id, received_at = raw.content, raw.source_id, raw.received_at

        trading = await self.runtime.get(TradingRuntime)
        stale = datetime.now(UTC) - received_at > timedelta(minutes=trading.signal_ttl_minutes)

        # Don't spend LLM calls on catch-up messages that are already too old to act on.
        outcome = await self.parse_text(text, allow_llm=not stale)
        p = outcome.parsed
        if not p.is_signal:
            await self._finish_raw(
                raw_message_id, RawMessageStatus.IGNORED, p.reason, cause, outcome.llm_error
            )
            return None

        if p.side is None:  # unreachable: is_signal implies a side
            return None
        instrument = await self.instruments.resolve(p)
        problems: list[str] = list(p.warnings)
        if instrument is None:
            problems.append("instrument not found (sync instruments or edit the signal)")
        if p.entry_ref is None:
            problems.append("no entry price")
        if stale:
            status = SignalStatus.EXPIRED
            problems.append("message older than the signal expiry window")
        elif (
            instrument is not None
            and p.entry_ref is not None
            and p.stop_loss is not None
            and not any("wrong side" in w for w in p.warnings)
            and p.confidence >= trading.min_confidence
        ):
            status = SignalStatus.VALIDATED
        else:
            status = SignalStatus.NEW  # needs review

        details: dict[str, Any] = {
            "underlying": p.underlying,
            "instrument_type": p.instrument_type.value if p.instrument_type else None,
            "strike": str(p.strike) if p.strike is not None else None,
            "expiry_text": p.expiry_text,
            "warnings": problems,
        }
        if outcome.llm_error:
            details["llm_error"] = outcome.llm_error
        async with self.sf() as s:
            sig = Signal(
                source_id=source_id,
                raw_message_id=raw_message_id,
                instrument_id=instrument.id if instrument else None,
                symbol_text=(p.symbol_text or "?")[:128],
                side=p.side,
                entry_low=p.entry_low,
                entry_high=p.entry_high,
                stop_loss=p.stop_loss,
                targets=[str(t) for t in p.targets],
                confidence=p.confidence,
                status=status,
                parser=outcome.parser or SignalParser.RULE,
                notes="; ".join(problems) or None,
                details=details,
            )
            s.add(sig)
            await s.commit()
            await s.refresh(sig)

        await self._finish_raw(raw_message_id, RawMessageStatus.PARSED, None, cause, None)
        payload = {
            "symbol_text": sig.symbol_text,
            "side": sig.side,
            "status": sig.status,
            "parser": sig.parser,
            "confidence": str(sig.confidence),
            "raw_message_id": str(raw_message_id),
        }
        ev = (
            cause.caused(
                EventType.SIGNAL_CREATED,
                aggregate_type="signal",
                aggregate_id=sig.id,
                payload=payload,
            )
            if cause
            else Event(
                type=EventType.SIGNAL_CREATED,
                aggregate_type="signal",
                aggregate_id=sig.id,
                payload=payload,
            )
        )
        await self.bus.publish(ev)
        return sig

    async def _finish_raw(
        self,
        raw_id: uuid.UUID,
        status: RawMessageStatus,
        reason: str | None,
        cause: Event | None,
        llm_error: str | None,
    ) -> None:
        async with self.sf() as s:
            raw = await s.get(RawMessage, raw_id)
            if raw is None:
                return
            raw.status = status
            raw.payload = {**raw.payload, "parse_reason": reason, "llm_error": llm_error}
            await s.commit()
        payload = {"status": status, "reason": reason}
        ev = (
            cause.caused(
                EventType.RAW_MESSAGE_PROCESSED,
                aggregate_type="raw_message",
                aggregate_id=raw_id,
                payload=payload,
            )
            if cause
            else Event(
                type=EventType.RAW_MESSAGE_PROCESSED,
                aggregate_type="raw_message",
                aggregate_id=raw_id,
                payload=payload,
            )
        )
        await self.bus.publish(ev)

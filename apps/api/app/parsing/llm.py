"""LLM fallback parser: asks Claude to extract a structured trade signal."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.adapters.llm import LLMAdapter, LLMMessage, LLMRequest
from app.models.enums import InstrumentType, Side
from app.parsing.models import ParsedSignal, sanity_check

SYSTEM_PROMPT = """You extract trading signals from Indian stock-market Telegram messages \
(NSE/BSE equities, NFO index and stock options/futures).

Return is_signal=true only when the message is a NEW actionable trade call that names an \
instrument and a direction. Status updates ("target 1 hit", "SL hit", "book profit"), \
commentary, ads and greetings are not signals.

Rules:
- side: BUY or SELL. Option calls without a verb are BUY.
- symbol_text: the instrument as written, normalised, e.g. "NIFTY 24500 CE", "RELIANCE", \
"TATAMOTORS FUT".
- underlying: the stock or index name, e.g. NIFTY, BANKNIFTY, FINNIFTY, RELIANCE.
- instrument_type: EQ, FUT, CE or PE.
- Prices are plain decimal strings. Use null for anything not stated; never invent numbers.
- entry_low/entry_high: the entry price or range ("above 120" -> both 120).
- targets: every target price in order.
- confidence: 0 to 1, how sure you are this is a complete, correctly read signal.
- reason: a short note (why it is not a signal, or any ambiguity)."""


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [schema, {"type": "null"}]}


_STR = _nullable({"type": "string"})
_NUM = _nullable({"type": "string", "description": "decimal number as a string"})

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "is_signal": {"type": "boolean"},
        "reason": _STR,
        "side": _nullable({"type": "string", "enum": ["BUY", "SELL"]}),
        "symbol_text": _STR,
        "underlying": _STR,
        "instrument_type": _nullable({"type": "string", "enum": ["EQ", "FUT", "CE", "PE"]}),
        "strike": _NUM,
        "expiry_text": _STR,
        "entry_low": _NUM,
        "entry_high": _NUM,
        "stop_loss": _NUM,
        "targets": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
    },
    "required": [
        "is_signal",
        "reason",
        "side",
        "symbol_text",
        "underlying",
        "instrument_type",
        "strike",
        "expiry_text",
        "entry_low",
        "entry_high",
        "stop_loss",
        "targets",
        "confidence",
    ],
    "additionalProperties": False,
}


def _dec(v: object) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        d = Decimal(str(v).replace(",", "").strip())
    except InvalidOperation:
        return None
    return d if d > 0 else None


def to_parsed(data: dict[str, Any]) -> ParsedSignal:
    """Validate untrusted model output into a ParsedSignal."""
    side = data.get("side")
    typ = data.get("instrument_type")
    conf = Decimal(str(max(0.0, min(float(data.get("confidence") or 0), 1.0)))).quantize(
        Decimal("0.001")
    )
    p = ParsedSignal(
        is_signal=bool(data.get("is_signal")),
        reason=data.get("reason"),
        side=Side(side) if side in ("BUY", "SELL") else None,
        symbol_text=(data.get("symbol_text") or None),
        underlying=(data.get("underlying") or None),
        instrument_type=InstrumentType(typ) if typ in ("EQ", "FUT", "CE", "PE") else None,
        strike=_dec(data.get("strike")),
        expiry_text=data.get("expiry_text") or None,
        entry_low=_dec(data.get("entry_low")),
        entry_high=_dec(data.get("entry_high")),
        stop_loss=_dec(data.get("stop_loss")),
        targets=[d for t in (data.get("targets") or []) if (d := _dec(t)) is not None],
        confidence=conf,
    )
    if p.is_signal and (p.side is None or not p.symbol_text):
        p.is_signal = False
        p.reason = "model output missing side or instrument"
    if p.symbol_text:
        p.symbol_text = p.symbol_text.upper()[:128]
    if p.underlying:
        p.underlying = p.underlying.upper()[:64]
    issues = sanity_check(p)
    if issues:
        p.warnings.extend(issues)
        p.confidence = max(Decimal("0"), p.confidence - Decimal("0.45"))
    if p.is_signal and p.stop_loss is None:
        p.warnings.append("no stop loss given")
    return p


async def parse_llm(adapter: LLMAdapter, text: str) -> ParsedSignal:
    resp = await adapter.complete(
        LLMRequest(
            messages=[
                LLMMessage(role="system", content=SYSTEM_PROMPT),
                LLMMessage(role="user", content=f"<message>\n{text[:4000]}\n</message>"),
            ],
            max_tokens=2048,
            response_schema=RESPONSE_SCHEMA,
        )
    )
    return to_parsed(resp.parsed or {})

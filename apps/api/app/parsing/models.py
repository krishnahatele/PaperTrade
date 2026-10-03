"""Parser output shared by the rule-based and LLM parsers."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import InstrumentType, Side


class ParsedSignal(BaseModel):
    is_signal: bool
    reason: str | None = Field(default=None, description="Why it is not a signal / caveats")
    side: Side | None = None
    symbol_text: str | None = Field(default=None, description="Symbol as written, normalised")
    underlying: str | None = None
    instrument_type: InstrumentType | None = None
    strike: Decimal | None = None
    expiry_text: str | None = None
    entry_low: Decimal | None = None
    entry_high: Decimal | None = None
    stop_loss: Decimal | None = None
    targets: list[Decimal] = Field(default_factory=list)
    confidence: Decimal = Decimal("0")
    warnings: list[str] = Field(default_factory=list)

    @property
    def entry_ref(self) -> Decimal | None:
        """Representative entry price (midpoint of the range)."""
        if self.entry_low is not None and self.entry_high is not None:
            return (self.entry_low + self.entry_high) / 2
        return self.entry_low or self.entry_high


def sanity_check(p: ParsedSignal) -> list[str]:
    """Price-level consistency: BUY wants SL < entry < targets, SELL the reverse."""
    issues: list[str] = []
    entry = p.entry_ref
    if p.side is None or entry is None:
        return issues
    buy = p.side is Side.BUY
    if p.stop_loss is not None and (p.stop_loss >= entry if buy else p.stop_loss <= entry):
        issues.append("stop loss is on the wrong side of entry")
    bad = [t for t in p.targets if (t <= entry if buy else t >= entry)]
    if bad:
        issues.append("target(s) on the wrong side of entry")
    return issues

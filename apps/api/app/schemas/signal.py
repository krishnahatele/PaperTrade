from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.models.enums import Side, SignalParser, SignalStatus
from app.schemas.common import ReadModel


class SignalBase(BaseModel):
    source_id: uuid.UUID
    instrument_id: uuid.UUID | None = None
    symbol_text: str = Field(min_length=1, max_length=128)
    side: Side
    entry_low: Decimal | None = Field(default=None, gt=0)
    entry_high: Decimal | None = Field(default=None, gt=0)
    stop_loss: Decimal | None = Field(default=None, gt=0)
    targets: list[Decimal] = Field(default_factory=list)
    notes: str | None = None

    @model_validator(mode="after")
    def _entry_range(self) -> SignalBase:
        if (
            self.entry_low is not None
            and self.entry_high is not None
            and self.entry_low > self.entry_high
        ):
            raise ValueError("entry_low must be <= entry_high")
        return self


class SignalCreate(SignalBase):
    """Manual signal entry. Automated parsing arrives in a later phase."""


class SignalRead(SignalBase, ReadModel):
    raw_message_id: uuid.UUID | None
    confidence: Decimal | None
    status: SignalStatus
    parser: SignalParser
    details: dict[str, Any]


class SignalReview(BaseModel):
    """Manual review: approve/reject, or fix fields the parser got wrong."""

    status: SignalStatus | None = None
    instrument_id: uuid.UUID | None = None
    entry_low: Decimal | None = Field(default=None, gt=0)
    entry_high: Decimal | None = Field(default=None, gt=0)
    stop_loss: Decimal | None = Field(default=None, gt=0)
    targets: list[Decimal] | None = None
    notes: str | None = None


class ParsePreviewBody(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    use_llm: bool = True
    force_llm: bool = Field(default=False, description="Skip the rules parser and ask the AI")


class ParsePreview(BaseModel):
    parser: SignalParser | None
    is_signal: bool
    reason: str | None
    side: str | None
    symbol_text: str | None
    underlying: str | None
    instrument_type: str | None
    strike: Decimal | None
    expiry_text: str | None
    entry_low: Decimal | None
    entry_high: Decimal | None
    stop_loss: Decimal | None
    targets: list[Decimal]
    confidence: Decimal
    warnings: list[str]
    llm_error: str | None
    instrument_id: uuid.UUID | None
    instrument_tradingsymbol: str | None

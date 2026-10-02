from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.enums import Side, SignalParser, SignalStatus


class Signal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A structured trade idea derived from a raw message or entered manually."""

    __tablename__ = "signals"
    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("signal_sources.id", ondelete="RESTRICT"), index=True
    )
    raw_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("raw_messages.id", ondelete="SET NULL"), index=True
    )
    instrument_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("instruments.id", ondelete="RESTRICT"), index=True
    )
    # The symbol exactly as written in the source, before instrument resolution.
    symbol_text: Mapped[str] = mapped_column(String(128))
    side: Mapped[Side] = mapped_column(str_enum(Side, "side"))
    entry_low: Mapped[Decimal | None]
    entry_high: Mapped[Decimal | None]
    stop_loss: Mapped[Decimal | None]
    # List of target prices serialised as strings to preserve decimal precision.
    targets: Mapped[list[Any]] = mapped_column(default=list)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    status: Mapped[SignalStatus] = mapped_column(
        str_enum(SignalStatus, "signal_status"), default=SignalStatus.NEW, index=True
    )
    parser: Mapped[SignalParser] = mapped_column(
        str_enum(SignalParser, "signal_parser"), default=SignalParser.MANUAL
    )
    notes: Mapped[str | None] = mapped_column(Text)

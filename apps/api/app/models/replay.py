from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.enums import ExitReason, ReplayOutcome, ReplayStatus, Side


class ReplayRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A backtest of past Telegram signals against historical prices.

    Fully separate from live paper trading: it never touches orders, trades,
    positions or the paper account."""

    __tablename__ = "replay_runs"

    name: Mapped[str] = mapped_column(String(128))
    status: Mapped[ReplayStatus] = mapped_column(
        str_enum(ReplayStatus, "replay_status"), default=ReplayStatus.QUEUED, index=True
    )
    params: Mapped[dict[str, Any]] = mapped_column(default=dict)
    progress: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    report: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]


class ReplayTrade(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One message of a replay and what would have happened to it."""

    __tablename__ = "replay_trades"

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("replay_runs.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("signal_sources.id", ondelete="SET NULL")
    )
    source_name: Mapped[str] = mapped_column(String(255))
    message_id: Mapped[str | None] = mapped_column(String(64))
    message_text: Mapped[str] = mapped_column(Text)
    message_at: Mapped[datetime]
    outcome: Mapped[ReplayOutcome] = mapped_column(
        str_enum(ReplayOutcome, "replay_outcome"), index=True
    )
    instrument_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("instruments.id", ondelete="SET NULL")
    )
    tradingsymbol: Mapped[str | None] = mapped_column(String(64))
    segment: Mapped[str | None] = mapped_column(String(16))
    side: Mapped[Side | None] = mapped_column(str_enum(Side, "side"))
    # The parsed call: entry range, stop, targets, parser, confidence
    signal: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    quantity: Mapped[int | None]
    entry_price: Mapped[Decimal | None]
    entry_at: Mapped[datetime | None]
    exit_price: Mapped[Decimal | None]
    exit_at: Mapped[datetime | None]
    exit_reason: Mapped[ExitReason | None] = mapped_column(str_enum(ExitReason, "exit_reason"))
    targets_hit: Mapped[int] = mapped_column(default=0, server_default="0")
    gross_pnl: Mapped[Decimal | None]
    charges: Mapped[Decimal | None]
    net_pnl: Mapped[Decimal | None]
    r_multiple: Mapped[Decimal | None]
    # Best / worst move in our favour / against us while in the trade, per unit
    mfe: Mapped[Decimal | None]
    mae: Mapped[Decimal | None]
    legs: Mapped[list[Any]] = mapped_column(default=list, server_default="[]")
    notes: Mapped[str | None] = mapped_column(Text)

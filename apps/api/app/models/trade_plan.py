from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.enums import ExitReason, ProductType, Side, TradePlanStatus


class TradePlan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One managed trade: an entry order, then a stop-loss for the open quantity and
    one target order per take-profit leg (TP1, TP2, ...). Partial exits reduce
    ``open_quantity``; the plan closes when it reaches zero."""

    __tablename__ = "trade_plans"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)

    signal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("signals.id", ondelete="SET NULL"), index=True
    )
    broker_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("broker_accounts.id", ondelete="CASCADE"), index=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="RESTRICT"), index=True
    )
    side: Mapped[Side] = mapped_column(str_enum(Side, "side"))
    product: Mapped[ProductType] = mapped_column(str_enum(ProductType, "product_type"))
    quantity: Mapped[int]
    status: Mapped[TradePlanStatus] = mapped_column(
        str_enum(TradePlanStatus, "trade_plan_status"),
        default=TradePlanStatus.PENDING,
        index=True,
    )
    planned_entry: Mapped[Decimal | None]
    stop_loss: Mapped[Decimal]
    # The signal's stop before any trailing (used for R-multiples and display).
    initial_stop_loss: Mapped[Decimal | None]
    # First target (kept for lists); the full ladder is in ``targets``.
    target: Mapped[Decimal | None]
    # [{"price": "610", "quantity": 20, "status": "open|hit|cancelled"}, ...]
    targets: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    # {"mode": "none|step|points|percent", "value": "5"}
    trailing: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    open_quantity: Mapped[int] = mapped_column(default=0, server_default="0")
    # Best price seen since entry (high for longs, low for shorts) for trailing.
    best_price: Mapped[Decimal | None]
    entry_price: Mapped[Decimal | None]
    exit_price: Mapped[Decimal | None]  # average over all exits
    # Gross P&L of everything exited so far; realized_pnl = gross - charges.
    gross_pnl: Mapped[Decimal | None]
    realized_pnl: Mapped[Decimal | None]
    charges: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    exit_reason: Mapped[ExitReason | None] = mapped_column(str_enum(ExitReason, "exit_reason"))
    opened_at: Mapped[datetime | None]
    closed_at: Mapped[datetime | None]
    notes: Mapped[str | None] = mapped_column(Text)

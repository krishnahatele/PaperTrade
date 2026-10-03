from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Trade(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A fill (full or partial execution) against an order."""

    __tablename__ = "trades"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    broker_trade_id: Mapped[str | None] = mapped_column(String(64))
    quantity: Mapped[int]
    price: Mapped[Decimal]
    executed_at: Mapped[datetime]

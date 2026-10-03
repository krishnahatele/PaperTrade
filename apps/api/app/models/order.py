from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.enums import (
    ExecutionMode,
    OrderRole,
    OrderStatus,
    OrderType,
    OrderValidity,
    ProductType,
    Side,
)


class Order(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An order intent and its lifecycle state, in paper or (later) live mode."""

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint(
            "filled_quantity >= 0 AND filled_quantity <= quantity", name="filled_quantity_range"
        ),
    )

    broker_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("broker_accounts.id", ondelete="RESTRICT"), index=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="RESTRICT"), index=True
    )
    signal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("signals.id", ondelete="SET NULL"), index=True
    )
    # Idempotency key we generate; prevents duplicate submissions.
    client_order_id: Mapped[str] = mapped_column(String(64), unique=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(64), index=True)
    mode: Mapped[ExecutionMode] = mapped_column(str_enum(ExecutionMode, "execution_mode"))
    side: Mapped[Side] = mapped_column(str_enum(Side, "side"))
    order_type: Mapped[OrderType] = mapped_column(str_enum(OrderType, "order_type"))
    product: Mapped[ProductType] = mapped_column(str_enum(ProductType, "product_type"))
    validity: Mapped[OrderValidity] = mapped_column(
        str_enum(OrderValidity, "order_validity"), default=OrderValidity.DAY
    )
    quantity: Mapped[int]
    price: Mapped[Decimal | None]
    trigger_price: Mapped[Decimal | None]
    status: Mapped[OrderStatus] = mapped_column(
        str_enum(OrderStatus, "order_status"), default=OrderStatus.CREATED, index=True
    )
    filled_quantity: Mapped[int] = mapped_column(default=0)
    average_price: Mapped[Decimal | None]
    status_message: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None]
    # Bracket management: which trade plan this order belongs to, and its job in it.
    trade_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trade_plans.id", ondelete="SET NULL"), index=True
    )
    role: Mapped[OrderRole] = mapped_column(
        str_enum(OrderRole, "order_role"), default=OrderRole.MANUAL, server_default="manual"
    )
    # Working orders past this time are cancelled (unfilled signal entries).
    expires_at: Mapped[datetime | None]
    # For TARGET orders: which take-profit leg (0 = TP1) this order exits.
    leg: Mapped[int | None]

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.enums import ProductType


class Position(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Net holding per account / instrument / product. Negative quantity = short."""

    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("broker_account_id", "instrument_id", "product"),)

    broker_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("broker_accounts.id", ondelete="CASCADE"), index=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="RESTRICT"), index=True
    )
    product: Mapped[ProductType] = mapped_column(str_enum(ProductType, "product_type"))
    quantity: Mapped[int] = mapped_column(default=0)
    average_price: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    realized_pnl: Mapped[Decimal] = mapped_column(default=Decimal("0"))

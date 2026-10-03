from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.enums import Exchange, InstrumentType


class Instrument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A tradable contract (equity, future, option, index)."""

    __tablename__ = "instruments"
    __table_args__ = (
        UniqueConstraint("exchange", "tradingsymbol"),
        # Derivative lookup by underlying: name + type + nearest expiry.
        Index("ix_instruments_name_type_expiry", "name", "instrument_type", "expiry"),
    )

    exchange: Mapped[Exchange] = mapped_column(str_enum(Exchange, "exchange"))
    tradingsymbol: Mapped[str] = mapped_column(String(64))
    name: Mapped[str | None] = mapped_column(String(255))
    instrument_type: Mapped[InstrumentType] = mapped_column(
        str_enum(InstrumentType, "instrument_type")
    )
    # Broker-specific numeric token (e.g. Kite instrument_token). Nullable until synced.
    instrument_token: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    segment: Mapped[str | None] = mapped_column(String(32))
    expiry: Mapped[date | None]
    strike: Mapped[Decimal | None]
    lot_size: Mapped[int] = mapped_column(default=1)
    tick_size: Mapped[Decimal] = mapped_column(default=Decimal("0.05"))
    is_active: Mapped[bool] = mapped_column(default=True)
    # Other brokers' ids for this contract, e.g. {"dhan": "49081"}.
    broker_refs: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")

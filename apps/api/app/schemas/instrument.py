from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import Exchange, InstrumentType
from app.schemas.common import ReadModel


class InstrumentBase(BaseModel):
    exchange: Exchange
    tradingsymbol: str = Field(min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=255)
    instrument_type: InstrumentType
    instrument_token: int | None = None
    segment: str | None = Field(default=None, max_length=32)
    expiry: date | None = None
    strike: Decimal | None = None
    lot_size: int = Field(default=1, gt=0)
    tick_size: Decimal = Field(default=Decimal("0.05"), gt=0)
    is_active: bool = True


class InstrumentCreate(InstrumentBase):
    pass


class InstrumentRead(InstrumentBase, ReadModel):
    pass

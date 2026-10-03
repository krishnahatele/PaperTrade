from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import ExitReason, OrderType, ProductType, Side, TradePlanStatus
from app.schemas.common import ReadModel


class TradePlanRead(ReadModel):
    signal_id: uuid.UUID | None
    broker_account_id: uuid.UUID
    instrument_id: uuid.UUID
    side: Side
    product: ProductType
    quantity: int
    status: TradePlanStatus
    planned_entry: Decimal | None
    stop_loss: Decimal
    target: Decimal | None
    entry_price: Decimal | None
    exit_price: Decimal | None
    realized_pnl: Decimal | None
    charges: Decimal
    exit_reason: ExitReason | None
    opened_at: datetime | None
    closed_at: datetime | None
    # enriched
    tradingsymbol: str | None = None
    ltp: Decimal | None = None
    unrealized_pnl: Decimal | None = None


class ManualOrderBody(BaseModel):
    broker_account_id: uuid.UUID | None = None
    instrument_id: uuid.UUID
    side: Side
    quantity: int = Field(gt=0)
    order_type: OrderType = OrderType.MARKET
    price: Decimal | None = Field(default=None, gt=0)
    trigger_price: Decimal | None = Field(default=None, gt=0)


class ExecuteBody(BaseModel):
    broker_account_id: uuid.UUID | None = None


class ManualPriceBody(BaseModel):
    instrument_id: uuid.UUID
    price: Decimal = Field(gt=0)


class LtpRead(BaseModel):
    instrument_id: uuid.UUID
    tradingsymbol: str
    ltp: Decimal | None


class PositionView(BaseModel):
    id: uuid.UUID
    broker_account_id: uuid.UUID
    instrument_id: uuid.UUID
    tradingsymbol: str
    product: ProductType
    quantity: int
    average_price: Decimal
    realized_pnl: Decimal
    ltp: Decimal | None
    unrealized_pnl: Decimal | None


class AccountSummary(BaseModel):
    broker_account_id: uuid.UUID
    label: str
    mode: str
    capital: Decimal
    realized_today: Decimal
    realized_total: Decimal
    unrealized: Decimal
    open_trades: int
    pending_trades: int
    closed_trades: int
    win_rate: Decimal | None


class KiteSessionBody(BaseModel):
    request_token: str = Field(
        min_length=8, max_length=2000, description="Token or full redirect URL"
    )

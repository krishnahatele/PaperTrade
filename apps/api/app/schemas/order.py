from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from app.models.enums import (
    ExecutionMode,
    OrderStatus,
    OrderType,
    OrderValidity,
    ProductType,
    Side,
)
from app.schemas.common import ReadModel


class OrderRead(ReadModel):
    broker_account_id: uuid.UUID
    instrument_id: uuid.UUID
    signal_id: uuid.UUID | None
    client_order_id: str
    broker_order_id: str | None
    mode: ExecutionMode
    side: Side
    order_type: OrderType
    product: ProductType
    validity: OrderValidity
    quantity: int
    price: Decimal | None
    trigger_price: Decimal | None
    status: OrderStatus
    filled_quantity: int
    average_price: Decimal | None
    status_message: str | None
    submitted_at: datetime | None


class TradeRead(ReadModel):
    order_id: uuid.UUID
    broker_trade_id: str | None
    quantity: int
    price: Decimal
    executed_at: datetime


class PositionRead(ReadModel):
    broker_account_id: uuid.UUID
    instrument_id: uuid.UUID
    product: ProductType
    quantity: int
    average_price: Decimal
    realized_pnl: Decimal

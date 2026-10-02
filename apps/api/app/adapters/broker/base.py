"""BrokerAdapter: the only boundary through which orders may leave MarketOS.

Implementations (planned): ``PaperBrokerAdapter`` (simulated fills, Phase 2+)
and ``KiteBrokerAdapter`` (Zerodha Kite Connect, gated behind explicit live
enablement in a later phase). Phase 0 ships the interface and a disabled stub.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from pydantic import BaseModel, Field

from app.adapters.base import AdapterHealth
from app.models.enums import (
    Exchange,
    ExecutionMode,
    OrderStatus,
    OrderType,
    OrderValidity,
    ProductType,
    Side,
)


class BrokerOrderRequest(BaseModel):
    client_order_id: str
    exchange: Exchange
    tradingsymbol: str
    side: Side
    quantity: int = Field(gt=0)
    order_type: OrderType
    product: ProductType
    validity: OrderValidity = OrderValidity.DAY
    price: Decimal | None = None
    trigger_price: Decimal | None = None


class BrokerOrderAck(BaseModel):
    client_order_id: str
    broker_order_id: str
    status: OrderStatus


class BrokerOrderUpdate(BaseModel):
    broker_order_id: str
    status: OrderStatus
    filled_quantity: int = 0
    average_price: Decimal | None = None
    message: str | None = None


class BrokerPosition(BaseModel):
    exchange: Exchange
    tradingsymbol: str
    product: ProductType
    quantity: int
    average_price: Decimal


class BrokerAdapter(ABC):
    name: str
    mode: ExecutionMode

    @abstractmethod
    async def health(self) -> AdapterHealth: ...

    @abstractmethod
    async def place_order(self, request: BrokerOrderRequest) -> BrokerOrderAck: ...

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> BrokerOrderUpdate: ...

    @abstractmethod
    async def get_order(self, broker_order_id: str) -> BrokerOrderUpdate: ...

    @abstractmethod
    async def get_positions(self) -> list[BrokerPosition]: ...

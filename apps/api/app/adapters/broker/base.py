"""BrokerAdapter: the only boundary through which orders may leave MarketOS.

Implementations: ``KiteBrokerAdapter`` and ``DhanBrokerAdapter``. Read-only
calls (profile, funds, positions) are used today to test a connection. The
order methods exist and are unit-tested, but nothing in the trading engine
routes orders to them: live execution needs the layered opt-in described in
``docs/architecture.md`` (safety model) and is a later phase.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from pydantic import BaseModel, Field

from app.adapters.base import AdapterHealth
from app.core.errors import FeatureDisabledError
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
    # Broker's own id for the contract (Dhan securityId, ...), when it has one.
    security_id: str | None = None
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


class BrokerProfile(BaseModel):
    user_id: str
    name: str | None = None
    detail: dict[str, str] = Field(default_factory=dict)


class BrokerFunds(BaseModel):
    available: Decimal
    used: Decimal | None = None
    detail: dict[str, str] = Field(default_factory=dict)


class BrokerOrderChange(BaseModel):
    quantity: int | None = Field(default=None, gt=0)
    price: Decimal | None = None
    trigger_price: Decimal | None = None
    order_type: OrderType | None = None


class BrokerAdapter(ABC):
    """Every method that can move money is in this class and nowhere else."""

    name: str
    mode: ExecutionMode

    def _unsupported(self, what: str) -> FeatureDisabledError:
        return FeatureDisabledError(f"{self.name} does not support {what}.")

    async def profile(self) -> BrokerProfile:
        raise self._unsupported("reading the profile")

    async def funds(self) -> BrokerFunds:
        raise self._unsupported("reading funds")

    async def modify_order(self, broker_order_id: str, change: BrokerOrderChange) -> None:
        raise self._unsupported("modifying orders")

    async def exit_all(self) -> None:
        raise self._unsupported("exit all")

    async def set_kill_switch(self, on: bool) -> None:
        raise self._unsupported("a kill switch")

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

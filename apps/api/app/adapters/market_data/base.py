"""MarketDataAdapter: last-traded prices (polled). Implementations: Kite, Dhan."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.adapters.base import AdapterHealth
from app.models.enums import Exchange


class InstrumentKey(BaseModel):
    exchange: Exchange
    tradingsymbol: str
    # Broker-specific ids, filled when known (Dhan quotes need these).
    security_id: str | None = None
    segment: str | None = None


class Quote(BaseModel):
    instrument: InstrumentKey
    last_price: Decimal
    timestamp: datetime
    bid: Decimal | None = None
    ask: Decimal | None = None
    volume: int | None = None


TickHandler = Callable[[Quote], Awaitable[None]]


class MarketDataAdapter(ABC):
    name: str

    @abstractmethod
    async def health(self) -> AdapterHealth: ...

    @abstractmethod
    async def get_quotes(self, instruments: Sequence[InstrumentKey]) -> list[Quote]: ...

    @abstractmethod
    async def subscribe(
        self, instruments: Sequence[InstrumentKey], on_tick: TickHandler
    ) -> None: ...

    @abstractmethod
    async def unsubscribe(self, instruments: Sequence[InstrumentKey]) -> None: ...

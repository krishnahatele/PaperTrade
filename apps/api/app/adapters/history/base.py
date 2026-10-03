"""HistoryAdapter: past minute candles for replay / backtesting."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.core.errors import MarketOSError
from app.models import Instrument


class Candle(BaseModel):
    ts: datetime  # candle start, UTC
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int = 0


class HistoryUnavailableError(MarketOSError):
    status_code = 424
    code = "history_unavailable"


class HistoryAdapter(ABC):
    name: str

    @abstractmethod
    async def minute_candles(self, inst: Instrument, day_from: date, day_to: date) -> list[Candle]:
        """1-minute candles for ``inst`` between two dates (inclusive), oldest first.

        Raises ``HistoryUnavailableError`` when the source cannot serve it
        (e.g. an expired contract)."""

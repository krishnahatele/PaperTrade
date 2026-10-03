from __future__ import annotations

from collections.abc import Sequence

from app.adapters.base import AdapterHealth, AdapterState
from app.adapters.market_data.base import InstrumentKey, MarketDataAdapter, Quote, TickHandler
from app.core.errors import FeatureDisabledError

_MSG = "Market data is not available in Phase 0."


class DisabledMarketDataAdapter(MarketDataAdapter):
    name = "disabled"

    async def health(self) -> AdapterHealth:
        return AdapterHealth(name=self.name, state=AdapterState.DISABLED, detail=_MSG)

    async def get_quotes(self, instruments: Sequence[InstrumentKey]) -> list[Quote]:
        raise FeatureDisabledError(_MSG)

    async def subscribe(self, instruments: Sequence[InstrumentKey], on_tick: TickHandler) -> None:
        raise FeatureDisabledError(_MSG)

    async def unsubscribe(self, instruments: Sequence[InstrumentKey]) -> None:
        raise FeatureDisabledError(_MSG)

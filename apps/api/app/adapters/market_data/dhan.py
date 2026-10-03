"""Dhan market data: LTP via ``/marketfeed/ltp`` (needs Dhan's Data API plan)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from app.adapters.base import AdapterHealth, AdapterState
from app.adapters.broker.dhan import DhanClient
from app.adapters.market_data.base import InstrumentKey, MarketDataAdapter, Quote, TickHandler
from app.core.errors import FeatureDisabledError


class DhanMarketDataAdapter(MarketDataAdapter):
    name = "dhan"
    MAX_PER_CALL = 1000

    def __init__(self, client: DhanClient) -> None:
        self.client = client

    async def health(self) -> AdapterHealth:
        return AdapterHealth(name=self.name, state=AdapterState.READY, detail="Dhan data API")

    async def get_quotes(self, instruments: Sequence[InstrumentKey]) -> list[Quote]:
        keyed = [i for i in instruments if i.security_id and i.segment]
        out: list[Quote] = []
        now = datetime.now(UTC)
        for start in range(0, len(keyed), self.MAX_PER_CALL):
            chunk = keyed[start : start + self.MAX_PER_CALL]
            by_segment: dict[str, list[int]] = {}
            for k in chunk:
                by_segment.setdefault(str(k.segment), []).append(int(str(k.security_id)))
            data = await self.client.ltp(by_segment)
            for k in chunk:
                row = (data.get(str(k.segment)) or {}).get(str(k.security_id))
                if row and row.get("last_price") is not None:
                    out.append(
                        Quote(
                            instrument=k, last_price=Decimal(str(row["last_price"])), timestamp=now
                        )
                    )
        return out

    async def subscribe(self, instruments: Sequence[InstrumentKey], on_tick: TickHandler) -> None:
        raise FeatureDisabledError("Streaming is not used; prices are polled.")

    async def unsubscribe(self, instruments: Sequence[InstrumentKey]) -> None:
        return None

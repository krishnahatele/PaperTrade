"""Last-traded prices for the instruments we care about.

The source is picked in Settings (BrokerRuntime.market_data): Kite when a
session is active, else Dhan (Data API plan). Without either, prices can be set
manually (paper trading practice / tests)."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import TYPE_CHECKING

from app.adapters.base import AdapterHealth, AdapterState
from app.adapters.market_data import DisabledMarketDataAdapter, InstrumentKey, MarketDataAdapter
from app.core.logging import get_logger
from app.models import Instrument
from app.services.kite import KiteService
from app.services.runtime import BrokerRuntime, DataSource, RuntimeStore

if TYPE_CHECKING:
    from app.services.brokers import BrokerService

log = get_logger("marketos.market_data")

MarketDataFactory = Callable[[str, str], MarketDataAdapter]


def build_kite(api_key: str, access_token: str) -> MarketDataAdapter:
    from app.adapters.market_data.kite import KiteMarketDataAdapter

    return KiteMarketDataAdapter(api_key, access_token)


class MarketDataService:
    CACHE_SECONDS = 1.5

    def __init__(
        self,
        kite: KiteService,
        factory: MarketDataFactory = build_kite,
        brokers: BrokerService | None = None,
        runtime: RuntimeStore | None = None,
    ) -> None:
        self.kite = kite
        self.factory = factory
        self.brokers = brokers
        self.runtime = runtime
        self.adapter: MarketDataAdapter = DisabledMarketDataAdapter()
        self.live = False
        self.manual: dict[uuid.UUID, Decimal] = {}
        self._cache: dict[uuid.UUID, tuple[float, Decimal]] = {}
        self.last_error: str | None = None

    async def reload(self) -> None:
        source = (
            (await self.runtime.get(BrokerRuntime)).market_data
            if self.runtime is not None
            else DataSource.AUTO
        )
        self.adapter, self.live = DisabledMarketDataAdapter(), False
        if source in (DataSource.AUTO, DataSource.KITE):
            creds = await self.kite.credentials()
            if creds:
                self.adapter, self.live = self.factory(*creds), True
        if not self.live and source in (DataSource.AUTO, DataSource.DHAN) and self.brokers:
            client = await self.brokers.dhan_client()
            if client is not None:
                from app.adapters.market_data.dhan import DhanMarketDataAdapter

                self.adapter, self.live = DhanMarketDataAdapter(client), True
        self._cache.clear()
        self.last_error = None

    def set_manual(self, instrument_id: uuid.UUID, price: Decimal) -> None:
        self.manual[instrument_id] = price
        self._cache.pop(instrument_id, None)

    async def ltp(self, instruments: Sequence[Instrument]) -> dict[uuid.UUID, Decimal]:
        out: dict[uuid.UUID, Decimal] = {}
        now = time.monotonic()
        todo: list[Instrument] = []
        for inst in instruments:
            hit = self._cache.get(inst.id)
            if hit and now - hit[0] < self.CACHE_SECONDS:
                out[inst.id] = hit[1]
            else:
                todo.append(inst)
        if todo and self.live:
            try:
                quotes = await self.adapter.get_quotes([_key(i) for i in todo])
                by_key = {(q.instrument.exchange, q.instrument.tradingsymbol): q for q in quotes}
                for inst in todo:
                    q = by_key.get((inst.exchange, inst.tradingsymbol))
                    if q is not None:
                        out[inst.id] = q.last_price
                        self._cache[inst.id] = (now, q.last_price)
                self.last_error = None
            except Exception as exc:
                self.last_error = getattr(exc, "message", None) or f"{type(exc).__name__}: {exc}"
                log.warning("market_data.quote_failed", error=self.last_error)
        for inst in todo:
            if inst.id not in out and inst.id in self.manual:
                out[inst.id] = self.manual[inst.id]
        return out

    async def health(self) -> AdapterHealth:
        name = self.adapter.name
        if self.last_error:
            return AdapterHealth(name=name, state=AdapterState.ERROR, detail=self.last_error)
        if self.live:
            return AdapterHealth(
                name=name,
                state=AdapterState.READY,
                detail=f"Live prices from {name.capitalize()}",
            )
        return AdapterHealth(
            name="manual",
            state=AdapterState.NOT_CONFIGURED,
            detail="Log in to Kite or connect Dhan for live prices (manual prices only).",
        )


def _key(i: Instrument) -> InstrumentKey:
    from app.adapters.broker.dhan import dhan_segment

    sec = (i.broker_refs or {}).get("dhan")
    return InstrumentKey(
        exchange=i.exchange,
        tradingsymbol=i.tradingsymbol,
        security_id=str(sec) if sec else None,
        segment=dhan_segment(i.exchange, i.instrument_type) if sec else None,
    )

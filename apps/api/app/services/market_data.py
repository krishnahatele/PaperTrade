"""Last-traded prices for the instruments we care about.

Source of truth is Kite when a session is active. Without Kite, prices can be
set manually (paper trading practice / tests)."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Sequence
from decimal import Decimal

from app.adapters.base import AdapterHealth, AdapterState
from app.adapters.market_data import DisabledMarketDataAdapter, InstrumentKey, MarketDataAdapter
from app.core.logging import get_logger
from app.models import Instrument
from app.services.kite import KiteService

log = get_logger("marketos.market_data")

MarketDataFactory = Callable[[str, str], MarketDataAdapter]


def build_kite(api_key: str, access_token: str) -> MarketDataAdapter:
    from app.adapters.market_data.kite import KiteMarketDataAdapter

    return KiteMarketDataAdapter(api_key, access_token)


class MarketDataService:
    CACHE_SECONDS = 1.5

    def __init__(self, kite: KiteService, factory: MarketDataFactory = build_kite) -> None:
        self.kite = kite
        self.factory = factory
        self.adapter: MarketDataAdapter = DisabledMarketDataAdapter()
        self.live = False
        self.manual: dict[uuid.UUID, Decimal] = {}
        self._cache: dict[uuid.UUID, tuple[float, Decimal]] = {}
        self.last_error: str | None = None

    async def reload(self) -> None:
        creds = await self.kite.credentials()
        if creds:
            self.adapter, self.live = self.factory(*creds), True
        else:
            self.adapter, self.live = DisabledMarketDataAdapter(), False
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
                quotes = await self.adapter.get_quotes(
                    [
                        InstrumentKey(exchange=i.exchange, tradingsymbol=i.tradingsymbol)
                        for i in todo
                    ]
                )
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
        if self.last_error:
            return AdapterHealth(name="kite", state=AdapterState.ERROR, detail=self.last_error)
        if self.live:
            return AdapterHealth(
                name="kite", state=AdapterState.READY, detail="Live prices from Kite"
            )
        return AdapterHealth(
            name="manual",
            state=AdapterState.NOT_CONFIGURED,
            detail="Log in to Kite for live prices (manual prices only).",
        )

"""Historical minute candles for replay, from Kite or Dhan (Settings → data source)."""

from __future__ import annotations

from datetime import date

from app.adapters.history.base import Candle, HistoryAdapter, HistoryUnavailableError
from app.models import Instrument
from app.services.brokers import BrokerService
from app.services.kite import KiteService
from app.services.runtime import BrokerRuntime, DataSource, RuntimeStore


class HistoryService:
    def __init__(self, kite: KiteService, brokers: BrokerService, runtime: RuntimeStore) -> None:
        self.kite = kite
        self.brokers = brokers
        self.runtime = runtime
        self.override: HistoryAdapter | None = None  # tests

    async def sources(self) -> list[HistoryAdapter]:
        """Adapters to try, in order of preference."""
        if self.override is not None:
            return [self.override]
        pref = (await self.runtime.get(BrokerRuntime)).history
        out: list[HistoryAdapter] = []
        if pref in (DataSource.AUTO, DataSource.KITE):
            creds = await self.kite.credentials()
            if creds:
                from app.adapters.history.kite import KiteHistoryAdapter

                out.append(KiteHistoryAdapter(*creds))
        if pref in (DataSource.AUTO, DataSource.DHAN):
            client = await self.brokers.dhan_client()
            if client is not None:
                from app.adapters.history.dhan import DhanHistoryAdapter

                out.append(DhanHistoryAdapter(client))
        return out

    async def candles(
        self, inst: Instrument, day_from: date, day_to: date, sources: list[HistoryAdapter]
    ) -> tuple[list[Candle], str]:
        """Candles from the first source that has them; returns (candles, source name)."""
        if not sources:
            raise HistoryUnavailableError(
                "No historical data source: log in to Kite or connect Dhan in Settings."
            )
        errors = []
        for src in sources:
            try:
                candles = await src.minute_candles(inst, day_from, day_to)
            except HistoryUnavailableError as exc:
                errors.append(f"{src.name}: {exc.message}")
                continue
            if candles:
                return candles, src.name
            errors.append(f"{src.name}: no candles")
        raise HistoryUnavailableError("; ".join(errors))

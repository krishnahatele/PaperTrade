"""Kite Connect market data (REST LTP polling; the official client is synchronous,
so calls run in a worker thread)."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from kiteconnect import KiteConnect
from kiteconnect import exceptions as kex

from app.adapters.base import AdapterHealth, AdapterState
from app.adapters.market_data.base import InstrumentKey, MarketDataAdapter, Quote, TickHandler
from app.core.errors import FeatureDisabledError, MarketOSError


class KiteSessionExpiredError(MarketOSError):
    status_code = 401
    code = "kite_session_expired"


class KiteError(MarketOSError):
    status_code = 502
    code = "kite_error"


class KiteMarketDataAdapter(MarketDataAdapter):
    name = "kite"
    MAX_PER_CALL = 500

    def __init__(self, api_key: str, access_token: str) -> None:
        self._kite = KiteConnect(api_key=api_key, access_token=access_token, timeout=10)

    async def health(self) -> AdapterHealth:
        return AdapterHealth(name=self.name, state=AdapterState.READY, detail="Kite session active")

    async def get_quotes(self, instruments: Sequence[InstrumentKey]) -> list[Quote]:
        keys = [f"{i.exchange.value}:{i.tradingsymbol}" for i in instruments]
        by_key = {f"{i.exchange.value}:{i.tradingsymbol}": i for i in instruments}
        out: list[Quote] = []
        now = datetime.now(UTC)
        for start in range(0, len(keys), self.MAX_PER_CALL):
            chunk = keys[start : start + self.MAX_PER_CALL]
            try:
                data = await asyncio.to_thread(self._kite.ltp, chunk)
            except kex.TokenException as exc:
                raise KiteSessionExpiredError(
                    "Kite session expired. Log in to Kite again in Settings."
                ) from exc
            except kex.KiteException as exc:
                raise KiteError(f"Kite error: {exc}") from exc
            except Exception as exc:
                raise KiteError(f"Cannot reach Kite: {type(exc).__name__}") from exc
            for key, row in (data or {}).items():
                if key in by_key and row.get("last_price") is not None:
                    out.append(
                        Quote(
                            instrument=by_key[key],
                            last_price=Decimal(str(row["last_price"])),
                            timestamp=now,
                        )
                    )
        return out

    async def subscribe(self, instruments: Sequence[InstrumentKey], on_tick: TickHandler) -> None:
        raise FeatureDisabledError("Streaming is not used; prices are polled.")

    async def unsubscribe(self, instruments: Sequence[InstrumentKey]) -> None:
        return None

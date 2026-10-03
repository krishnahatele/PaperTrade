"""Kite Connect historical candles (needs a Kite Connect plan with historical data).

Kite does not serve expired F&O contracts, so replays of past weekly options
need Dhan's expired-options data instead."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from kiteconnect import KiteConnect
from kiteconnect import exceptions as kex

from app.adapters.history.base import Candle, HistoryAdapter, HistoryUnavailableError
from app.models import Instrument


class KiteHistoryAdapter(HistoryAdapter):
    name = "kite"
    MAX_DAYS = 60  # minute data per request

    def __init__(self, api_key: str, access_token: str, kite: Any | None = None) -> None:
        self._kite = kite or KiteConnect(api_key=api_key, access_token=access_token, timeout=30)

    async def minute_candles(self, inst: Instrument, day_from: date, day_to: date) -> list[Candle]:
        if inst.instrument_token is None:
            raise HistoryUnavailableError(f"{inst.tradingsymbol} has no Kite instrument token.")
        out: list[Candle] = []
        start = day_from
        while start <= day_to:
            end = min(day_to, start + timedelta(days=self.MAX_DAYS - 1))
            try:
                rows = await asyncio.to_thread(
                    self._kite.historical_data,
                    inst.instrument_token,
                    datetime.combine(start, time(0, 0)),
                    datetime.combine(end, time(23, 59)),
                    "minute",
                )
            except kex.TokenException as exc:
                raise HistoryUnavailableError("Kite session expired; log in again.") from exc
            except kex.KiteException as exc:
                raise HistoryUnavailableError(f"Kite: {exc}") from exc
            for r in rows or []:
                ts = r["date"]
                ts = ts.astimezone(UTC) if ts.tzinfo else ts.replace(tzinfo=UTC)
                out.append(
                    Candle(
                        ts=ts,
                        open=Decimal(str(r["open"])),
                        high=Decimal(str(r["high"])),
                        low=Decimal(str(r["low"])),
                        close=Decimal(str(r["close"])),
                        volume=int(r.get("volume") or 0),
                    )
                )
            start = end + timedelta(days=1)
        return out

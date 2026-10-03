"""Dhan historical candles (Data API plan).

* Live / recent contracts: ``/charts/intraday`` by security id.
* Expired index options: ``/charts/rollingoption`` returns minute data for
  "ATM+n" strikes; we scan offsets and keep the minutes where the strike equals
  the contract's strike.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.adapters.broker.dhan import (
    INDEX_SECURITY_IDS,
    DhanClient,
    dhan_instrument,
    dhan_segment,
    epoch_to_utc,
)
from app.adapters.history.base import Candle, HistoryAdapter, HistoryUnavailableError
from app.core.errors import MarketOSError
from app.models import Instrument
from app.models.enums import InstrumentType


def _candles(data: dict[str, Any], strike: Decimal | None = None) -> list[Candle]:
    ts = data.get("timestamp") or []
    o, h, lo, c = (data.get(k) or [] for k in ("open", "high", "low", "close"))
    vol = data.get("volume") or []
    strikes = data.get("strike") or []
    out = []
    for i, t in enumerate(ts):
        if strike is not None and (i >= len(strikes) or Decimal(str(strikes[i])) != strike):
            continue
        try:
            out.append(
                Candle(
                    ts=epoch_to_utc(t),
                    open=Decimal(str(o[i])),
                    high=Decimal(str(h[i])),
                    low=Decimal(str(lo[i])),
                    close=Decimal(str(c[i])),
                    volume=int(vol[i]) if i < len(vol) and vol[i] is not None else 0,
                )
            )
        except (IndexError, ArithmeticError):
            continue
    return out


class DhanHistoryAdapter(HistoryAdapter):
    name = "dhan"
    MAX_DAYS = 5  # intraday minute data per request
    ATM_SCAN = 10  # strikes either side of ATM to scan for expired options

    def __init__(self, client: DhanClient) -> None:
        self.client = client

    async def minute_candles(self, inst: Instrument, day_from: date, day_to: date) -> list[Candle]:
        sec = (inst.broker_refs or {}).get("dhan")
        if sec:
            out: list[Candle] = []
            start = day_from
            while start <= day_to:
                end = min(day_to, start + timedelta(days=self.MAX_DAYS - 1))
                try:
                    data = await self.client.intraday(
                        str(sec),
                        dhan_segment(inst.exchange, inst.instrument_type),
                        dhan_instrument(inst.exchange, inst.instrument_type, inst.name),
                        start,
                        end + timedelta(days=1),
                    )
                except MarketOSError as exc:
                    raise HistoryUnavailableError(f"Dhan: {exc.message}") from exc
                out.extend(_candles(data))
                start = end + timedelta(days=1)
            if out:
                return out
        if inst.instrument_type in (InstrumentType.CE, InstrumentType.PE):
            return await self._expired_option(inst, day_from, day_to)
        raise HistoryUnavailableError(f"No Dhan data for {inst.tradingsymbol}.")

    async def _expired_option(self, inst: Instrument, day_from: date, day_to: date) -> list[Candle]:
        und = (inst.name or "").upper()
        und_id = INDEX_SECURITY_IDS.get(und)
        if und_id is None or inst.strike is None:
            raise HistoryUnavailableError(
                f"No expired-option data for {inst.tradingsymbol} (index options only)."
            )
        kind = "CALL" if inst.instrument_type is InstrumentType.CE else "PUT"
        flag = (
            "MONTH"
            if inst.expiry and (inst.expiry + timedelta(days=7)).month != inst.expiry.month
            else "WEEK"
        )
        found: dict[Any, Candle] = {}
        for off in range(-self.ATM_SCAN, self.ATM_SCAN + 1):
            strike = "ATM" if off == 0 else f"ATM{off:+d}"
            try:
                data = await self.client.rolling_option(
                    und_id,
                    "NSE_FNO" if und not in ("SENSEX", "BANKEX") else "BSE_FNO",
                    "OPTIDX",
                    flag,
                    1,
                    strike,
                    kind,
                    day_from,
                    day_to + timedelta(days=1),
                )
            except MarketOSError:
                continue
            series = (data.get("data") or {}).get("ce" if kind == "CALL" else "pe") or {}
            for candle in _candles(series, inst.strike):
                found[candle.ts] = candle
        if not found:
            raise HistoryUnavailableError(f"Dhan has no data for expired {inst.tradingsymbol}.")
        return [found[k] for k in sorted(found)]

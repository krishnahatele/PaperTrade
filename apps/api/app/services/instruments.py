"""Instrument master: sync from Kite's public instrument dump, and resolve signal symbols."""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import MarketOSError
from app.events import Event, EventBus, EventType
from app.models import Instrument
from app.models.enums import Exchange, InstrumentType, Segment
from app.parsing.models import ParsedSignal

KITE_DUMP_URL = "https://api.kite.trade/instruments/{exchange}"
DEFAULT_SYNC_EXCHANGES = (Exchange.NSE, Exchange.NFO, Exchange.BSE, Exchange.BFO, Exchange.MCX)
DERIVATIVE_EXCHANGES = (Exchange.NFO, Exchange.BFO, Exchange.MCX)


def segment_of(inst: Instrument) -> Segment:
    """Equity / F&O / Commodity / Currency, for reports and trading hours."""
    if inst.instrument_type is InstrumentType.INDEX:
        return Segment.INDEX
    if inst.exchange is Exchange.MCX:
        return Segment.COMMODITY
    if inst.exchange is Exchange.CDS:
        return Segment.CURRENCY
    if inst.exchange in (Exchange.NFO, Exchange.BFO):
        return Segment.FNO
    return Segment.EQUITY


CsvFetcher = Callable[[Exchange], Awaitable[str]]


class InstrumentSyncError(MarketOSError):
    status_code = 502
    code = "instrument_sync_failed"


async def fetch_kite_dump(exchange: Exchange) -> str:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.get(KITE_DUMP_URL.format(exchange=exchange.value))
            r.raise_for_status()
            return r.text
    except httpx.HTTPError as exc:
        raise InstrumentSyncError(f"Could not download {exchange} instruments: {exc}") from exc


def _dec(s: str) -> Decimal | None:
    try:
        d = Decimal(s)
    except (InvalidOperation, TypeError):
        return None
    return d if d != 0 else None


def parse_kite_csv(text: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for r in csv.DictReader(io.StringIO(text)):
        try:
            exchange = Exchange(r["exchange"])
        except ValueError:
            continue
        if r.get("segment") == "INDICES":
            typ = InstrumentType.INDEX
        else:
            try:
                typ = InstrumentType(r["instrument_type"])
            except ValueError:
                continue
        expiry = date.fromisoformat(r["expiry"]) if r.get("expiry") else None
        rows.append(
            {
                "exchange": exchange,
                "tradingsymbol": r["tradingsymbol"],
                "name": (r.get("name") or None),
                "instrument_type": typ,
                "instrument_token": int(r["instrument_token"]),
                "segment": r.get("segment") or None,
                "expiry": expiry,
                "strike": _dec(r.get("strike", "")),
                "lot_size": max(int(r.get("lot_size") or 1), 1),
                "tick_size": _dec(r.get("tick_size", "")) or Decimal("0.05"),
                "is_active": True,
            }
        )
    return rows


class InstrumentService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        bus: EventBus,
        fetcher: CsvFetcher = fetch_kite_dump,
    ) -> None:
        self.sf = session_factory
        self.bus = bus
        self.fetcher = fetcher

    async def sync(self, exchanges: Sequence[Exchange] = DEFAULT_SYNC_EXCHANGES) -> dict[str, int]:
        counts: dict[str, int] = {}
        today = datetime.now(UTC).date()
        for ex in exchanges:
            rows = parse_kite_csv(await self.fetcher(ex))
            async with self.sf() as s:
                for i in range(0, len(rows), 2000):
                    chunk = rows[i : i + 2000]
                    for row in chunk:
                        row["id"] = uuid.uuid4()
                    stmt = insert(Instrument).values(chunk)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["exchange", "tradingsymbol"],
                        set_={
                            c: stmt.excluded[c]
                            for c in (
                                "name",
                                "instrument_type",
                                "instrument_token",
                                "segment",
                                "expiry",
                                "strike",
                                "lot_size",
                                "tick_size",
                                "is_active",
                            )
                        },
                    )
                    await s.execute(stmt)
                # Expired derivatives are kept for history but marked inactive.
                await s.execute(
                    update(Instrument)
                    .where(Instrument.exchange == ex, Instrument.expiry < today)
                    .values(is_active=False)
                )
                await s.commit()
            counts[ex.value] = len(rows)
        await self.bus.publish(
            Event(type=EventType.INSTRUMENTS_SYNCED, aggregate_type="instrument", payload=counts)
        )
        return counts

    async def resolve(self, p: ParsedSignal, as_of: date | None = None) -> Instrument | None:
        """Map a parsed signal to a concrete instrument (nearest expiry for F&O / MCX).

        ``as_of`` resolves as of a past day (replay): expired contracts count if
        they were live then.
        """
        if not p.symbol_text or p.instrument_type is None:
            return None
        und = (p.underlying or p.symbol_text).upper()
        day = as_of or datetime.now(UTC).date()
        live_only = as_of is None
        async with self.sf() as s:
            if p.instrument_type is InstrumentType.EQ:
                for ex in (Exchange.NSE, Exchange.BSE):
                    q = select(Instrument).where(
                        Instrument.exchange == ex, Instrument.tradingsymbol == und
                    )
                    if live_only:
                        q = q.where(Instrument.is_active.is_(True))
                    inst = await s.scalar(q)
                    if inst is not None:
                        return inst
                # Commodities trade only as futures: "BUY CRUDEOIL 6400 SL 6350"
                q = select(Instrument).where(
                    Instrument.exchange == Exchange.MCX,
                    Instrument.name == und,
                    Instrument.instrument_type == InstrumentType.FUT,
                    Instrument.expiry >= day,
                )
                if live_only:
                    q = q.where(Instrument.is_active.is_(True))
                return await s.scalar(q.order_by(Instrument.expiry).limit(1))
            q = select(Instrument).where(
                Instrument.name == und,
                Instrument.instrument_type == p.instrument_type,
                Instrument.expiry >= day,
                Instrument.exchange.in_(DERIVATIVE_EXCHANGES),
            )
            if live_only:
                q = q.where(Instrument.is_active.is_(True))
            if p.instrument_type in (InstrumentType.CE, InstrumentType.PE):
                if p.strike is None:
                    return None
                q = q.where(Instrument.strike == p.strike)
            month = _expiry_month(p.expiry_text)
            if month is not None:
                year = day.year + (1 if month < day.month - 6 else 0)
                q = q.where(Instrument.expiry >= date(year, month, 1))
            return await s.scalar(q.order_by(Instrument.expiry).limit(1))


_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def _expiry_month(text: str | None) -> int | None:
    if not text:
        return None
    for i, m in enumerate(_MONTHS, start=1):
        if m in text.upper():
            return i
    return None

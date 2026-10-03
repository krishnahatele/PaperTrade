"""Instrument master: sync from Kite's public instrument dump, and resolve signal symbols."""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select, update
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
TextFetcher = Callable[[], Awaitable[str]]
DHAN_SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
# Our (Kite) index symbols -> Dhan IDX_I security ids.
DHAN_INDEX_IDS = {
    "NIFTY 50": "13",
    "NIFTY BANK": "25",
    "NIFTY FIN SERVICE": "27",
    "NIFTY MID SELECT": "442",
    "INDIA VIX": "21",
    "SENSEX": "51",
    "BANKEX": "69",
}


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


async def fetch_dhan_scrip_master() -> str:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.get(DHAN_SCRIP_MASTER_URL)
            r.raise_for_status()
            return r.text
    except httpx.HTTPError as exc:
        raise InstrumentSyncError(f"Could not download Dhan's instrument list: {exc}") from exc


def _strike_key(v: Decimal | None) -> str:
    return "" if v is None else format(v.normalize(), "f")


def _deriv_key(
    ex: Exchange, typ: InstrumentType, und: str, expiry: date | None, strike: Decimal | None
) -> tuple[str, ...]:
    return (
        ex.value,
        typ.value,
        und.upper(),
        expiry.isoformat() if expiry else "",
        _strike_key(strike),
    )


def parse_dhan_master(text: str) -> dict[tuple[str, ...], str]:
    """Dhan scrip master rows -> {our matching key: Dhan security id}."""
    out: dict[tuple[str, ...], str] = {}
    for r in csv.DictReader(io.StringIO(text)):
        exch = (r.get("SEM_EXM_EXCH_ID") or "").strip()
        seg = (r.get("SEM_SEGMENT") or "").strip()
        sec = (r.get("SEM_SMST_SECURITY_ID") or "").strip()
        name = (r.get("SEM_INSTRUMENT_NAME") or "").strip()
        sym = (r.get("SEM_TRADING_SYMBOL") or "").strip()
        if not sec or not sym:
            continue
        if seg == "E" and exch in ("NSE", "BSE"):
            out[("EQ", exch, sym)] = sec
            continue
        if seg == "D" and exch in ("NSE", "BSE"):
            ex = Exchange.NFO if exch == "NSE" else Exchange.BFO
        elif seg == "M" and exch == "MCX":
            ex = Exchange.MCX
        else:
            continue
        if name.startswith("FUT"):
            typ = InstrumentType.FUT
        elif name.startswith("OPT"):
            opt = (r.get("SEM_OPTION_TYPE") or "").strip()
            if opt not in ("CE", "PE"):
                continue
            typ = InstrumentType(opt)
        else:
            continue
        raw_exp = (r.get("SEM_EXPIRY_DATE") or "").strip()[:10]
        try:
            expiry = date.fromisoformat(raw_exp) if raw_exp else None
        except ValueError:
            continue
        strike = _dec(r.get("SEM_STRIKE_PRICE") or "") if typ is not InstrumentType.FUT else None
        und = sym.split("-")[0]
        out[_deriv_key(ex, typ, und, expiry, strike)] = sec
    return out


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
        self.dhan_fetcher: TextFetcher = fetch_dhan_scrip_master

    async def sync_dhan_ids(self) -> dict[str, int]:
        """Attach Dhan security ids to our instruments (needed for Dhan prices,
        candles and orders). Run after the normal instrument sync."""
        ids = parse_dhan_master(await self.dhan_fetcher())
        updates: list[dict[str, object]] = []
        async with self.sf() as s:
            rows = await s.execute(
                select(
                    Instrument.id,
                    Instrument.exchange,
                    Instrument.tradingsymbol,
                    Instrument.name,
                    Instrument.instrument_type,
                    Instrument.expiry,
                    Instrument.strike,
                    Instrument.broker_refs,
                ).where(Instrument.is_active.is_(True))
            )
            for iid, ex, sym, name, typ, expiry, strike, refs in rows:
                if typ is InstrumentType.INDEX:
                    sec = DHAN_INDEX_IDS.get(sym)
                elif typ is InstrumentType.EQ:
                    sec = ids.get(("EQ", ex.value, sym))
                else:
                    sec = ids.get(_deriv_key(ex, typ, name or "", expiry, strike))
                if sec and (refs or {}).get("dhan") != sec:
                    updates.append({"id": iid, "broker_refs": {**(refs or {}), "dhan": sec}})
            for i in range(0, len(updates), 2000):
                await s.execute(update(Instrument), updates[i : i + 2000])
            await s.commit()
            mapped = await s.scalar(
                select(func.count()).where(Instrument.broker_refs.has_key("dhan"))
            )
        result = {"dhan_rows": len(ids), "updated": len(updates), "mapped": int(mapped or 0)}
        await self.bus.publish(
            Event(
                type=EventType.INSTRUMENTS_SYNCED,
                aggregate_type="instrument",
                payload={"broker": "dhan", **result},
            )
        )
        return result

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
                inst = await self._equity(s, und, live_only)
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

    async def _equity(self, s: AsyncSession, text: str, live_only: bool) -> Instrument | None:
        """A stock by symbol or by company name: "RELIANCE", "BELRISE INDUSTRIES",
        "LARSEN & TOUBRO", "TATA MOTORS" (NSE preferred over BSE)."""
        words = text.split()
        symbols = [text, text.replace(" ", ""), *([words[0]] if len(words) > 1 else [])]
        base = select(Instrument).where(
            Instrument.exchange.in_([Exchange.NSE, Exchange.BSE]),
            Instrument.instrument_type == InstrumentType.EQ,
        )
        if live_only:
            base = base.where(Instrument.is_active.is_(True))
        order = Instrument.exchange.desc()  # "NSE" > "BSE"
        for cond in (
            Instrument.tradingsymbol == symbols[0],
            Instrument.tradingsymbol == symbols[1],
            Instrument.name == text,
            Instrument.name.startswith(text + " "),
            *([Instrument.tradingsymbol == symbols[2]] if len(symbols) > 2 else []),
        ):
            inst = await s.scalar(base.where(cond).order_by(order).limit(1))
            if inst is not None:
                return inst
        return None

    async def explain_unresolved(self, p: ParsedSignal, as_of: date) -> str:
        """Why ``resolve`` found nothing, in plain words."""
        und = (p.underlying or p.symbol_text or "?").upper()
        async with self.sf() as s:
            if p.instrument_type is InstrumentType.EQ:
                return f"no stock or MCX future called {und} in your instrument list"
            total = await s.scalar(select(func.count()).where(Instrument.name == und))
            if not total:
                hint = (
                    " (SENSEX/BANKEX are on BSE: sync BFO)" if und in ("SENSEX", "BANKEX") else ""
                )
                return f"no {und} contracts in your instrument list: run Instruments → Sync{hint}"
            if p.instrument_type in (InstrumentType.CE, InstrumentType.PE) and p.strike is not None:
                any_strike = await s.scalar(
                    select(func.count()).where(
                        Instrument.name == und,
                        Instrument.strike == p.strike,
                        Instrument.instrument_type == p.instrument_type,
                    )
                )
                if not any_strike:
                    return (
                        f"{und} {p.strike} {p.instrument_type.value} is not in your "
                        f"instrument list (the contract for {as_of:%d %b} expired before "
                        "your last sync, or that strike isn't listed now)"
                    )
            return f"no {und} contract live on {as_of:%d %b} in your instrument list"


_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def _expiry_month(text: str | None) -> int | None:
    if not text:
        return None
    for i, m in enumerate(_MONTHS, start=1):
        if m in text.upper():
            return i
    return None

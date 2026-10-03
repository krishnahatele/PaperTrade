"""Market news and market-move alerts.

* News: RSS feeds (ET Markets, Moneycontrol, Mint, Business Standard, Google
  News searches, ...) polled every few minutes. Headlines that mention a watch
  keyword ("crude", "OPEC", "RBI", ...) become alerts: shown in the app and
  sent by the Telegram bot.
* Market moves: watched instruments (crude oil future, NIFTY, BANKNIFTY, VIX,
  gold, ...) are checked every minute; a move beyond the threshold inside the
  window raises an alert ("CRUDEOIL +2.1% in 30 min").
"""

from __future__ import annotations

import asyncio
import calendar
import hashlib
import re
import uuid
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger
from app.events import Event, EventBus, EventType
from app.models import Alert, Instrument, NewsItem
from app.models.enums import AlertKind, Exchange, InstrumentType
from app.services.market_data import MarketDataService
from app.services.runtime import RuntimeStore, register_runtime

log = get_logger("marketos.news")

UA = "Mozilla/5.0 (MarketOS news reader)"
UP_WORDS = r"surges?|soars?|jumps?|spikes?|rall(?:y|ies)|climbs?|rises?|gains?|hikes?|skyrockets?"
DOWN_WORDS = r"plunges?|crash(?:es)?|slumps?|tumbles?|falls?|drops?|declines?|slides?|sinks?|cuts?"


class Feed(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=8, max_length=1000)
    enabled: bool = True


class Watch(BaseModel):
    """A market-move alarm on one instrument (tradingsymbol, or an underlying
    name such as CRUDEOIL which resolves to its nearest future)."""

    symbol: str = Field(min_length=1, max_length=64)
    label: str = ""
    threshold_pct: Decimal = Field(default=Decimal("1"), gt=0, le=50)
    window_minutes: int = Field(default=30, ge=1, le=24 * 60)
    enabled: bool = True


DEFAULT_FEEDS = [
    Feed(
        name="ET Markets",
        url="https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    ),
    Feed(
        name="ET Commodities",
        url="https://economictimes.indiatimes.com/markets/commodities/rssfeeds/1808152121.cms",
    ),
    Feed(name="Moneycontrol Markets", url="https://www.moneycontrol.com/rss/marketreports.xml"),
    Feed(name="Moneycontrol Latest", url="https://www.moneycontrol.com/rss/latestnews.xml"),
    Feed(name="Mint Markets", url="https://www.livemint.com/rss/markets"),
    Feed(
        name="Business Standard Markets",
        url="https://www.business-standard.com/rss/markets-106.rss",
    ),
    Feed(
        name="Google News: crude oil",
        url="https://news.google.com/rss/search?q=crude+oil+price&hl=en-IN&gl=IN&ceid=IN:en",
    ),
    Feed(
        name="Google News: Nifty / Sensex",
        url="https://news.google.com/rss/search?q=nifty+OR+sensex&hl=en-IN&gl=IN&ceid=IN:en",
    ),
]
DEFAULT_KEYWORDS = [
    "crude",
    "brent",
    "OPEC",
    "RBI",
    "repo rate",
    "Fed",
    "inflation",
    "CPI",
    "GDP",
    "rupee",
    "gold",
    "war",
    "sanctions",
    "tariff",
    "Iran",
    "Israel",
    "Russia",
    "budget",
    "FII",
    "circuit",
    "SEBI",
]
DEFAULT_WATCHES = [
    Watch(symbol="CRUDEOIL", label="Crude oil (MCX)", threshold_pct=Decimal("1.5")),
    Watch(symbol="NIFTY 50", label="NIFTY", threshold_pct=Decimal("0.8"), window_minutes=15),
    Watch(symbol="NIFTY BANK", label="BANKNIFTY", threshold_pct=Decimal("1"), window_minutes=15),
    Watch(symbol="INDIA VIX", label="India VIX", threshold_pct=Decimal("8"), window_minutes=30),
    Watch(symbol="GOLD", label="Gold (MCX)", threshold_pct=Decimal("1")),
]


class NewsRuntime(BaseModel):
    enabled: bool = True
    poll_minutes: int = Field(default=5, ge=1, le=120)
    feeds: list[Feed] = Field(default_factory=lambda: list(DEFAULT_FEEDS))
    keywords: list[str] = Field(default_factory=lambda: list(DEFAULT_KEYWORDS))
    watches: list[Watch] = Field(default_factory=lambda: list(DEFAULT_WATCHES))
    market_alerts: bool = True
    alert_cooldown_minutes: int = Field(default=30, ge=1, le=24 * 60)


register_runtime(NewsRuntime, "news")


class FeedEntry(BaseModel):
    source: str
    title: str
    summary: str | None
    url: str
    published_at: datetime


class WatchState(BaseModel):
    symbol: str
    label: str
    tradingsymbol: str | None
    ltp: Decimal | None
    change_pct: Decimal | None
    window_minutes: int
    threshold_pct: Decimal


FeedFetcher = Callable[[Feed], Awaitable[str]]


async def fetch_feed(feed: Feed) -> str:
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        r = await client.get(feed.url, headers={"User-Agent": UA})
        r.raise_for_status()
        return r.text


def parse_feed(feed: Feed, text: str) -> list[FeedEntry]:
    import feedparser

    parsed = feedparser.parse(text)
    out: list[FeedEntry] = []
    now = datetime.now(UTC)
    for e in parsed.entries:
        title = re.sub(r"\s+", " ", str(e.get("title") or "")).strip()
        link = str(e.get("link") or "").strip()
        if not title or not link:
            continue
        ts = e.get("published_parsed") or e.get("updated_parsed")
        published = datetime.fromtimestamp(calendar.timegm(ts), UTC) if ts else now
        plain = re.sub(r"<[^>]+>", " ", str(e.get("summary") or ""))
        summary = re.sub(r"\s+", " ", plain).strip()[:600] or None
        out.append(
            FeedEntry(
                source=feed.name,
                title=title[:500],
                summary=summary,
                url=link[:1000],
                published_at=min(published, now),
            )
        )
    return out


def match_keywords(text: str, keywords: list[str]) -> list[str]:
    hits = []
    for kw in keywords:
        k = kw.strip()
        if not k:
            continue
        # Short all-caps words (RBI, Fed, CPI) match case-sensitively to avoid noise.
        flags = 0 if (k.isupper() or (k[:1].isupper() and len(k) <= 4)) else re.IGNORECASE
        if re.search(rf"(?<!\w){re.escape(k)}(?!\w)", text, flags):
            hits.append(k)
    return hits


def direction_of(text: str) -> str | None:
    t = text.lower()
    up = re.search(rf"\b({UP_WORDS})\b", t)
    down = re.search(rf"\b({DOWN_WORDS})\b", t)
    if up and (not down or up.start() < down.start()):
        return "up"
    if down:
        return "down"
    return None


class NewsService:
    ALERT_MAX_AGE = timedelta(hours=6)  # older headlines are stored but not alerted

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        bus: EventBus,
        runtime: RuntimeStore,
        market: MarketDataService,
        fetcher: FeedFetcher = fetch_feed,
    ) -> None:
        self.sf = session_factory
        self.bus = bus
        self.runtime = runtime
        self.market = market
        self.fetcher = fetcher
        self.last_poll: datetime | None = None
        self.feed_errors: dict[str, str] = {}
        self._history: dict[str, deque[tuple[datetime, Decimal]]] = {}
        self._last_alert: dict[str, datetime] = {}

    async def settings(self) -> NewsRuntime:
        return await self.runtime.get(NewsRuntime)

    # ------------------------------------------------------------------ news
    async def poll(self) -> dict[str, int]:
        cfg = await self.settings()
        feeds = [f for f in cfg.feeds if f.enabled]
        results = await asyncio.gather(*(self._fetch(f) for f in feeds))
        entries = [e for batch in results for e in batch]
        new_items = await self._store(entries, cfg.keywords)
        alerts = 0
        cutoff = datetime.now(UTC) - self.ALERT_MAX_AGE
        for item in new_items:
            await self.bus.publish(
                Event(
                    type=EventType.NEWS_RECEIVED,
                    aggregate_type="news",
                    aggregate_id=item.id,
                    payload={"source": item.source, "matched": item.matched},
                )
            )
            if item.matched and item.published_at >= cutoff and alerts < 5:
                alerts += 1
                await self._alert(
                    AlertKind.NEWS,
                    item.title,
                    f"{item.source} · matched: {', '.join(item.matched)}",
                    item.url,
                    {
                        "title": item.title,
                        "source": item.source,
                        "url": item.url,
                        "matched": item.matched,
                        "direction": item.direction,
                    },
                    EventType.NEWS_ALERT,
                )
        self.last_poll = datetime.now(UTC)
        return {"fetched": len(entries), "new": len(new_items), "alerts": alerts}

    async def _fetch(self, feed: Feed) -> list[FeedEntry]:
        try:
            entries = parse_feed(feed, await self.fetcher(feed))
        except Exception as exc:
            self.feed_errors[feed.name] = f"{type(exc).__name__}: {exc}"[:200]
            log.warning("news.feed_failed", feed=feed.name, error=self.feed_errors[feed.name])
            return []
        self.feed_errors.pop(feed.name, None)
        return entries

    async def _store(self, entries: list[FeedEntry], keywords: list[str]) -> list[NewsItem]:
        if not entries:
            return []
        seen: set[str] = set()
        rows = []
        for e in entries:
            key = hashlib.sha256(e.url.encode()).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            text = f"{e.title} {e.summary or ''}"
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "source": e.source,
                    "title": e.title,
                    "summary": e.summary,
                    "url": e.url,
                    "published_at": e.published_at,
                    "matched": match_keywords(text, keywords),
                    "direction": direction_of(e.title),
                }
            )
        async with self.sf() as s:
            stmt = insert(NewsItem).values(rows).on_conflict_do_nothing(index_elements=["url"])
            ids = list(await s.scalars(stmt.returning(NewsItem.id)))
            await s.commit()
            if not ids:
                return []
            return list(
                await s.scalars(
                    select(NewsItem).where(NewsItem.id.in_(ids)).order_by(NewsItem.published_at)
                )
            )

    async def _alert(
        self,
        kind: AlertKind,
        title: str,
        body: str | None,
        url: str | None,
        payload: dict[str, Any],
        event_type: str,
    ) -> None:
        async with self.sf() as s:
            alert = Alert(kind=kind, title=title[:500], body=body, url=url, payload=payload)
            s.add(alert)
            await s.commit()
            await s.refresh(alert)
        await self.bus.publish(
            Event(type=event_type, aggregate_type="alert", aggregate_id=alert.id, payload=payload)
        )

    async def prune(self, days: int = 14) -> None:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        async with self.sf() as s:
            await s.execute(delete(NewsItem).where(NewsItem.published_at < cutoff))
            await s.execute(delete(Alert).where(Alert.created_at < cutoff))
            await s.commit()

    # --------------------------------------------------------- market moves
    async def resolve_watch(self, w: Watch) -> Instrument | None:
        sym = w.symbol.strip().upper()
        async with self.sf() as s:
            inst = await s.scalar(
                select(Instrument)
                .where(Instrument.tradingsymbol == sym, Instrument.is_active.is_(True))
                .order_by(Instrument.exchange)
                .limit(1)
            )
            if inst is not None:
                return inst
            today = datetime.now(UTC).date()
            return await s.scalar(
                select(Instrument)
                .where(
                    Instrument.name == sym,
                    Instrument.instrument_type == InstrumentType.FUT,
                    Instrument.exchange.in_([Exchange.MCX, Exchange.NFO, Exchange.BFO]),
                    Instrument.is_active.is_(True),
                    Instrument.expiry >= today,
                )
                .order_by(Instrument.expiry)
                .limit(1)
            )

    async def check_moves(self, now: datetime | None = None) -> list[WatchState]:
        cfg = await self.settings()
        now = now or datetime.now(UTC)
        states: list[WatchState] = []
        resolved: list[tuple[Watch, Instrument | None]] = [
            (w, await self.resolve_watch(w)) for w in cfg.watches if w.enabled
        ]
        insts = [i for _, i in resolved if i is not None]
        prices = await self.market.ltp(insts) if insts else {}
        for w, inst in resolved:
            label = w.label or w.symbol
            ltp = prices.get(inst.id) if inst else None
            change: Decimal | None = None
            if inst is not None and ltp is not None:
                hist = self._history.setdefault(w.symbol, deque())
                hist.append((now, ltp))
                window_start = now - timedelta(minutes=w.window_minutes)
                while hist and hist[0][0] < window_start - timedelta(minutes=1):
                    hist.popleft()
                base_ts, base = hist[0]
                if base > 0 and now - base_ts >= timedelta(minutes=min(2, w.window_minutes)):
                    change = ((ltp - base) / base * 100).quantize(Decimal("0.01"))
                    cooled = now - self._last_alert.get(w.symbol, datetime.min.replace(tzinfo=UTC))
                    if (
                        cfg.market_alerts
                        and abs(change) >= w.threshold_pct
                        and cooled >= timedelta(minutes=cfg.alert_cooldown_minutes)
                    ):
                        self._last_alert[w.symbol] = now
                        mins = int((now - base_ts).total_seconds() // 60)
                        arrow = "▲" if change > 0 else "▼"
                        text = f"{label} {arrow} {change:+}% in {mins} min ({base} → {ltp})"
                        await self._alert(
                            AlertKind.MARKET,
                            text,
                            inst.tradingsymbol,
                            None,
                            {
                                "text": text,
                                "symbol": inst.tradingsymbol,
                                "change_pct": str(change),
                                "price": str(ltp),
                                "window_minutes": w.window_minutes,
                            },
                            EventType.MARKET_ALERT,
                        )
            states.append(
                WatchState(
                    symbol=w.symbol,
                    label=label,
                    tradingsymbol=inst.tradingsymbol if inst else None,
                    ltp=ltp,
                    change_pct=change,
                    window_minutes=w.window_minutes,
                    threshold_pct=w.threshold_pct,
                )
            )
        return states

    async def run_forever(self) -> None:
        next_news = datetime.now(UTC) + timedelta(seconds=15)
        while True:
            try:
                cfg = await self.settings()
                if cfg.enabled and datetime.now(UTC) >= next_news:
                    await self.poll()
                    await self.prune()
                    next_news = datetime.now(UTC) + timedelta(minutes=cfg.poll_minutes)
                if cfg.watches:
                    await self.check_moves()
            except Exception:
                log.exception("news.loop_failed")
            await asyncio.sleep(60)

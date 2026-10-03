"""News feed polling, keyword alerts, market-move alerts, delivery to the bot."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from email.utils import format_datetime

import pytest
from httpx import AsyncClient

from app.services.news import Feed, direction_of, match_keywords, parse_feed
from tests.fakes import KITE_CSV
from tests.test_paper_trading import ctr, price


def rss(*items: tuple[str, str, datetime]) -> str:
    body = "".join(
        f"<item><title>{t}</title><link>{u}</link>"
        f"<pubDate>{format_datetime(d)}</pubDate><description>&lt;p&gt;{t}&lt;/p&gt;</description></item>"
        for t, u, d in items
    )
    return (
        f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>{body}</channel></rss>'
    )


NOW = datetime.now(UTC)
FEED = rss(
    ("Crude oil surges 6% as OPEC cuts output", "https://news.example/crude", NOW),
    ("Nifty ends flat in choppy trade", "https://news.example/nifty", NOW),
    ("Old: RBI keeps repo rate unchanged", "https://news.example/rbi", NOW - timedelta(days=2)),
)


def test_parse_match_direction() -> None:
    entries = parse_feed(Feed(name="Test", url="https://x"), FEED)
    assert [e.title for e in entries][:2] == [
        "Crude oil surges 6% as OPEC cuts output",
        "Nifty ends flat in choppy trade",
    ]
    assert entries[0].summary == "Crude oil surges 6% as OPEC cuts output"
    assert match_keywords(entries[0].title, ["crude", "OPEC", "Fed", "gold"]) == ["crude", "OPEC"]
    assert match_keywords("Federal policy", ["Fed"]) == []  # whole words only
    assert direction_of("Crude oil surges 6%") == "up"
    assert direction_of("Nifty plunges 500 points") == "down"
    assert direction_of("Nifty ends flat") is None


@pytest.mark.db
async def test_poll_stores_dedupes_and_alerts(db_client: AsyncClient) -> None:
    c = db_client
    container = ctr(c)

    async def fetch(feed: Feed) -> str:
        return FEED

    container.news.fetcher = fetch
    await c.put(
        "/api/v1/news/settings",
        json={"feeds": [{"name": "Test", "url": "https://x"}], "keywords": ["crude", "RBI"]},
    )
    r = await c.post("/api/v1/news/refresh")
    assert r.json() == {"fetched": 3, "new": 3, "alerts": 1}  # the RBI item is too old to alert
    r = await c.post("/api/v1/news/refresh")
    assert r.json()["new"] == 0  # same URLs: stored once

    news = (await c.get("/api/v1/news", params={"matched_only": True})).json()
    assert news["total"] == 2
    alerts = (await c.get("/api/v1/alerts")).json()["items"]
    assert [a["kind"] for a in alerts] == ["news"]
    assert alerts[0]["payload"]["direction"] == "up"
    assert (await c.get("/api/v1/alerts/unread-count")).json() == {"unread": 1}
    await c.post("/api/v1/alerts/read-all")
    assert (await c.get("/api/v1/alerts/unread-count")).json() == {"unread": 0}

    r = await c.put("/api/v1/news/settings", json={"poll_minutes": 0})
    assert r.status_code == 422


@pytest.mark.db
async def test_market_move_alert(db_client: AsyncClient) -> None:
    c = db_client
    container = ctr(c)

    async def fetch_csv(_: object) -> str:
        return KITE_CSV

    container.instruments.fetcher = fetch_csv
    await c.post("/api/v1/instruments/sync", json={"exchanges": ["NSE", "MCX"]})
    await c.put(
        "/api/v1/news/settings",
        json={"watches": [{"symbol": "CRUDEOIL", "label": "Crude", "threshold_pct": 1.5}]},
    )
    fut = (await c.get("/api/v1/instruments", params={"q": "CRUDEOIL99JANFUT"})).json()["items"][0]
    t0 = datetime.now(UTC)
    await price(c, fut["id"], "6400")
    [s0] = await container.news.check_moves(t0)
    assert s0.tradingsymbol == "CRUDEOIL99JANFUT"
    await price(c, fut["id"], "6450")  # +0.8%: no alert
    await container.news.check_moves(t0 + timedelta(minutes=10))
    assert (await c.get("/api/v1/alerts")).json()["total"] == 0
    await price(c, fut["id"], "6530")  # +2.0% in 20 min
    [s] = await container.news.check_moves(t0 + timedelta(minutes=20))
    assert s.change_pct == Decimal("2.03")
    [a] = (await c.get("/api/v1/alerts")).json()["items"]
    assert a["kind"] == "market"
    assert a["title"].startswith("Crude ▲ +2.03% in 20 min")
    # cooldown: no second alert straight away
    await price(c, fut["id"], "6600")
    await container.news.check_moves(t0 + timedelta(minutes=25))
    assert (await c.get("/api/v1/alerts")).json()["total"] == 1

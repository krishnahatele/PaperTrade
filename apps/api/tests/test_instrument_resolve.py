"""Resolving parsed symbols to contracts across equity, F&O and MCX commodities."""

from datetime import date

import pytest
from httpx import AsyncClient

from app.models.enums import Segment
from app.parsing.rules import parse_rules
from app.services.instruments import segment_of
from tests.fakes import KITE_CSV
from tests.test_paper_trading import ctr

pytestmark = pytest.mark.db


async def synced(c: AsyncClient) -> None:
    async def fetch(_: object) -> str:
        return KITE_CSV

    ctr(c).instruments.fetcher = fetch
    r = await c.post("/api/v1/instruments/sync")
    assert r.status_code == 200, r.text


async def test_resolve_equity_fno_and_commodity(db_client: AsyncClient) -> None:
    await synced(db_client)
    svc = ctr(db_client).instruments
    cases = {
        "BUY RELIANCE 2450 SL 2420 TGT 2500": ("RELIANCE", Segment.EQUITY),
        "BUY NIFTY 24500 CE ABOVE 120 SL 100 TGT 140": ("NIFTY2610824500CE", Segment.FNO),
        "BUY CRUDE OIL 6400 SL 6350 TGT 6450": ("CRUDEOIL99JANFUT", Segment.COMMODITY),
        "BUY CRUDEOIL 6500 CE @ 120 SL 100 TGT 150": ("CRUDEOIL99JAN6500CE", Segment.COMMODITY),
    }
    for text, (symbol, segment) in cases.items():
        inst = await svc.resolve(parse_rules(text))
        assert inst is not None, text
        assert inst.tradingsymbol == symbol
        assert segment_of(inst) is segment


async def test_resolve_as_of_past_day_finds_expired_contract(db_client: AsyncClient) -> None:
    await synced(db_client)
    svc = ctr(db_client).instruments
    p = parse_rules("BUY NIFTY 24500 CE ABOVE 120 SL 100 TGT 140")
    inst = await svc.resolve(p, as_of=date(2019, 12, 30))
    assert inst is not None
    assert inst.tradingsymbol == "NIFTY2001024500CE"  # expired since, but live on that day

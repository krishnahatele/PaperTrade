"""Broker registry, Dhan client/adapters (mocked HTTP), Dhan id sync, price source."""

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from httpx import AsyncClient

from app.adapters.broker.base import BrokerOrderRequest
from app.adapters.broker.dhan import DhanBrokerAdapter, DhanClient, dhan_instrument
from app.adapters.history.dhan import DhanHistoryAdapter
from app.models import Instrument
from app.models.enums import Exchange, InstrumentType, OrderType, ProductType, Side
from app.services.instruments import parse_dhan_master
from app.services.runtime import BrokerRuntime
from tests.fakes import KITE_CSV
from tests.test_paper_trading import ctr

DHAN_MASTER = """\
SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_INSTRUMENT_NAME,SEM_EXPIRY_CODE,SEM_TRADING_SYMBOL,SEM_LOT_UNITS,SEM_CUSTOM_SYMBOL,SEM_EXPIRY_DATE,SEM_STRIKE_PRICE,SEM_OPTION_TYPE,SEM_TICK_SIZE,SEM_EXPIRY_FLAG,SEM_EXCH_INSTRUMENT_TYPE,SEM_SERIES,SM_SYMBOL_NAME
NSE,E,2885,EQUITY,0,RELIANCE,1.0,Reliance,,-0.01000,XX,5.0,NA,ES,EQ,RELIANCE INDUSTRIES
NSE,D,49081,OPTIDX,0,NIFTY-Jan2099-24500-CE,75.0,NIFTY 08 JAN 24500 CALL,2099-01-08 14:30:00,24500.00000,CE,5.0,W,OP,NA,
NSE,D,51234,FUTSTK,0,TATAMOTORS-Jan2099-FUT,550.0,TATAMOTORS JAN FUT,2099-01-29 14:30:00,-0.01000,XX,5.0,M,FUT,NA,
MCX,M,440001,FUTCOM,0,CRUDEOIL-19Jan2099-FUT,100.0,CRUDEOIL JAN FUT,2099-01-19 23:30:00,-0.01000,XX,100.0,M,FUT,NA,
"""


class FakeDhan:
    """A tiny in-memory Dhan API."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Any]] = []
        self.token_ok = True

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.path, body))
        path = request.url.path.removeprefix("/v2")
        if not self.token_ok or request.headers.get("access-token") != "tok-1":
            return httpx.Response(
                401, json={"errorCode": "DH-901", "errorMessage": "Invalid token"}
            )
        if path == "/profile":
            return httpx.Response(200, json={"dhanClientId": "1000001", "dataPlan": "Active"})
        if path == "/fundlimit":
            return httpx.Response(200, json={"availabelBalance": 50000.5, "utilizedAmount": 100})
        if path == "/positions" and request.method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        "tradingSymbol": "NIFTY-Jan2099-24500-CE",
                        "securityId": "49081",
                        "exchangeSegment": "NSE_FNO",
                        "productType": "INTRADAY",
                        "netQty": 75,
                        "costPrice": 120.5,
                    }
                ],
            )
        if path == "/marketfeed/ltp":
            return httpx.Response(
                200,
                json={"status": "success", "data": {"NSE_FNO": {"49081": {"last_price": 131.5}}}},
            )
        if path in ("/orders", "/super/orders"):
            return httpx.Response(200, json={"orderId": "9001", "orderStatus": "PENDING"})
        if path == "/charts/intraday":
            t0 = int(datetime(2099, 1, 2, 3, 45, tzinfo=UTC).timestamp())
            return httpx.Response(
                200,
                json={
                    "open": [100, 101],
                    "high": [102, 105],
                    "low": [99, 100],
                    "close": [101, 104],
                    "volume": [10, 20],
                    "timestamp": [t0, t0 + 60],
                },
            )
        if path == "/killswitch":
            return httpx.Response(200, json={"killSwitchStatus": "Kill Switch has been activated"})
        if path == "/RenewToken":
            return httpx.Response(200, json={"token": "tok-2"})
        return httpx.Response(404, json={"errorMessage": f"no route {path}"})


def test_dhan_instrument_names() -> None:
    assert dhan_instrument(Exchange.NFO, InstrumentType.CE, "NIFTY") == "OPTIDX"
    assert dhan_instrument(Exchange.NFO, InstrumentType.FUT, "TATAMOTORS") == "FUTSTK"
    assert dhan_instrument(Exchange.MCX, InstrumentType.FUT, "CRUDEOIL") == "FUTCOM"
    assert dhan_instrument(Exchange.MCX, InstrumentType.PE, "CRUDEOIL") == "OPTFUT"
    assert dhan_instrument(Exchange.NSE, InstrumentType.EQ, None) == "EQUITY"


def test_parse_dhan_master_keys() -> None:
    ids = parse_dhan_master(DHAN_MASTER)
    assert ids[("EQ", "NSE", "RELIANCE")] == "2885"
    assert ids[("NFO", "CE", "NIFTY", "2099-01-08", "24500")] == "49081"
    assert ids[("NFO", "FUT", "TATAMOTORS", "2099-01-29", "")] == "51234"
    assert ids[("MCX", "FUT", "CRUDEOIL", "2099-01-19", "")] == "440001"


async def test_dhan_order_payloads_and_super_order() -> None:
    fake = FakeDhan()
    client = DhanClient("1000001", "tok-1", httpx.MockTransport(fake))
    adapter = DhanBrokerAdapter(client)
    req = BrokerOrderRequest(
        client_order_id="mos-abc",
        exchange=Exchange.NFO,
        tradingsymbol="NIFTY2610824500CE",
        security_id="49081",
        side=Side.BUY,
        quantity=75,
        order_type=OrderType.LIMIT,
        product=ProductType.MIS,
        price=Decimal("120"),
    )
    ack = await adapter.place_super_order(req, Decimal("140"), Decimal("100"), Decimal("5"))
    assert ack.broker_order_id == "9001"
    method, path, body = fake.calls[-1]
    assert (method, path) == ("POST", "/v2/super/orders")
    assert body["dhanClientId"] == "1000001"
    assert body["exchangeSegment"] == "NSE_FNO"
    assert body["productType"] == "INTRADAY"
    assert body["securityId"] == "49081"
    assert (body["targetPrice"], body["stopLossPrice"], body["trailingJump"]) == (140, 100, 5)

    funds = await adapter.funds()
    assert funds.available == Decimal("50000.5")
    [pos] = await adapter.get_positions()
    assert pos.exchange is Exchange.NFO
    assert pos.product is ProductType.MIS
    assert pos.quantity == 75

    await adapter.set_kill_switch(True)
    assert fake.calls[-1][1] == "/v2/killswitch"
    await client.close()


async def test_dhan_bad_token_is_clear_error() -> None:
    fake = FakeDhan()
    client = DhanClient("1000001", "wrong", httpx.MockTransport(fake))
    health = await DhanBrokerAdapter(client).health()
    assert health.state == "error"
    assert "access token" in (health.detail or "")
    await client.close()


async def test_dhan_history_candles() -> None:
    client = DhanClient("1000001", "tok-1", httpx.MockTransport(FakeDhan()))
    inst = Instrument(
        exchange=Exchange.NFO,
        tradingsymbol="NIFTY2610824500CE",
        name="NIFTY",
        instrument_type=InstrumentType.CE,
        strike=Decimal("24500"),
        broker_refs={"dhan": "49081"},
    )
    candles = await DhanHistoryAdapter(client).minute_candles(
        inst, date(2099, 1, 2), date(2099, 1, 2)
    )
    assert [c.close for c in candles] == [Decimal("101"), Decimal("104")]
    assert candles[1].ts - candles[0].ts == timedelta(minutes=1)
    await client.close()


# ------------------------------------------------------------------ API (DB)
@pytest.mark.db
async def test_dhan_connect_test_prices_and_renew(db_client: AsyncClient) -> None:
    c = db_client
    container = ctr(c)
    fake = FakeDhan()
    container.brokers.dhan_transport = httpx.MockTransport(fake)

    providers = (await c.get("/api/v1/brokers/providers")).json()
    assert {p["id"] for p in providers} >= {"paper", "kite", "dhan"}
    r = await c.put("/api/v1/brokers/upstox/credentials", json={"values": {"x": "y"}})
    assert r.status_code == 403

    r = await c.put(
        "/api/v1/brokers/dhan/credentials",
        json={"values": {"client_id": "1000001", "access_token": "tok-1"}},
    )
    assert r.status_code == 200, r.text
    dhan = next(b for b in r.json() if b["info"]["id"] == "dhan")
    assert dhan["configured"] is True
    token = next(f for f in dhan["fields"] if f["name"] == "access_token")
    assert token["hint"] == "••••ok-1"  # masked, never the full value

    r = await c.post("/api/v1/brokers/dhan/test")
    t = r.json()
    assert t["ok"] is True, t
    assert t["profile"]["user_id"] == "1000001"
    assert t["positions"][0]["quantity"] == 75
    assert any("static IP" in n for n in t["notes"])
    assert all(call[0] == "GET" for call in fake.calls)  # read-only

    # Prices from Dhan once instruments carry Dhan ids
    async def fetch(_: object) -> str:
        return KITE_CSV

    async def dhan_master() -> str:
        return DHAN_MASTER

    container.instruments.fetcher = fetch
    container.instruments.dhan_fetcher = dhan_master
    await c.post("/api/v1/instruments/sync", json={"exchanges": ["NSE", "NFO", "MCX"]})
    r = await c.post("/api/v1/brokers/dhan/sync-instruments")
    # RELIANCE, NIFTY CE, TATAMOTORS FUT, CRUDEOIL FUT + the NIFTY 50 index (built-in id)
    assert r.json()["updated"] == 5
    r = await c.patch("/api/v1/brokers/settings", json={"market_data": "dhan"})
    assert r.status_code == 200, r.text
    ce = (await c.get("/api/v1/instruments", params={"q": "NIFTY2610824500CE"})).json()["items"][0]
    r = await c.get("/api/v1/market/ltp", params={"instrument_id": ce["id"]})
    assert r.json()[0]["ltp"] == "131.5"
    health = (await c.get("/api/v1/system/info")).json()
    assert "dhan" in json.dumps(health).lower()

    # Token renewal swaps in the new token
    await container.runtime.update(
        BrokerRuntime, dhan_token_saved_at=datetime.now(UTC) - timedelta(hours=21)
    )
    assert await container.brokers.renew_dhan_if_due() is True
    assert await container.secrets.get("broker.dhan.access_token") == "tok-2"

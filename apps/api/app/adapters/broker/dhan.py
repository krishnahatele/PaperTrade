"""DhanHQ v2 REST client and broker adapter.

Endpoints and field names follow Dhan's official ``dhanhq`` SDK (v2.2):
``https://api.dhan.co/v2`` with ``access-token`` / ``client-id`` headers.

Order placement needs a static IP whitelisted at Dhan (SEBI rule, April 2026)
and is not routed to from the trading engine in this build.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import httpx

from app.adapters.base import AdapterHealth, AdapterState
from app.adapters.broker.base import (
    BrokerAdapter,
    BrokerFunds,
    BrokerOrderAck,
    BrokerOrderChange,
    BrokerOrderRequest,
    BrokerOrderUpdate,
    BrokerPosition,
    BrokerProfile,
)
from app.core.errors import InvalidInputError, MarketOSError
from app.models.enums import (
    Exchange,
    ExecutionMode,
    InstrumentType,
    OrderStatus,
    OrderType,
    ProductType,
    Side,
)

API_BASE = "https://api.dhan.co/v2"
SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"

INDEX_UNDERLYINGS = {
    "NIFTY",
    "BANKNIFTY",
    "FINNIFTY",
    "MIDCPNIFTY",
    "NIFTYNXT50",
    "SENSEX",
    "BANKEX",
    "SENSEX50",
}
# Dhan security ids of the index spot series (IDX_I), used for expired-option data.
INDEX_SECURITY_IDS = {
    "NIFTY": "13",
    "BANKNIFTY": "25",
    "FINNIFTY": "27",
    "MIDCPNIFTY": "442",
    "SENSEX": "51",
    "BANKEX": "69",
}

_SEGMENT = {
    Exchange.NSE: "NSE_EQ",
    Exchange.BSE: "BSE_EQ",
    Exchange.NFO: "NSE_FNO",
    Exchange.BFO: "BSE_FNO",
    Exchange.MCX: "MCX_COMM",
    Exchange.CDS: "NSE_CURRENCY",
}
_EXCHANGE = {v: k for k, v in _SEGMENT.items()}
_PRODUCT = {ProductType.CNC: "CNC", ProductType.MIS: "INTRADAY", ProductType.NRML: "MARGIN"}
_PRODUCT_BACK = {v: k for k, v in _PRODUCT.items()}
_ORDER_TYPE = {
    OrderType.MARKET: "MARKET",
    OrderType.LIMIT: "LIMIT",
    OrderType.SL: "STOP_LOSS",
    OrderType.SL_M: "STOP_LOSS_MARKET",
}
_STATUS = {
    "TRANSIT": OrderStatus.SUBMITTED,
    "PENDING": OrderStatus.OPEN,
    "PART_TRADED": OrderStatus.PARTIALLY_FILLED,
    "TRADED": OrderStatus.FILLED,
    "CANCELLED": OrderStatus.CANCELLED,
    "REJECTED": OrderStatus.REJECTED,
    "EXPIRED": OrderStatus.CANCELLED,
}


class DhanError(MarketOSError):
    status_code = 502
    code = "dhan_error"


class DhanAuthError(DhanError):
    status_code = 401
    code = "dhan_auth_failed"


def dhan_segment(exchange: Exchange, instrument_type: InstrumentType) -> str:
    if instrument_type is InstrumentType.INDEX:
        return "IDX_I"
    return _SEGMENT[exchange]


def dhan_instrument(
    exchange: Exchange, instrument_type: InstrumentType, underlying: str | None
) -> str:
    """Dhan's instrument name for charts: EQUITY, INDEX, FUTIDX, OPTSTK, FUTCOM, ..."""
    if instrument_type is InstrumentType.INDEX:
        return "INDEX"
    if instrument_type is InstrumentType.EQ:
        return "EQUITY"
    option = instrument_type in (InstrumentType.CE, InstrumentType.PE)
    if exchange is Exchange.MCX:
        return "OPTFUT" if option else "FUTCOM"
    if exchange is Exchange.CDS:
        return "OPTCUR" if option else "FUTCUR"
    idx = (underlying or "").upper() in INDEX_UNDERLYINGS
    return ("OPT" if option else "FUT") + ("IDX" if idx else "STK")


def _dec(v: Any) -> Decimal:
    try:
        return Decimal(str(v))
    except ArithmeticError:
        return Decimal("0")


class DhanClient:
    """Thin async client. ``transport`` lets tests plug in ``httpx.MockTransport``."""

    MIN_QUOTE_INTERVAL = 1.05  # marketfeed: 1 request / second

    def __init__(
        self,
        client_id: str,
        access_token: str,
        transport: httpx.AsyncBaseTransport | None = None,
        base_url: str = API_BASE,
    ) -> None:
        self.client_id = client_id
        self.access_token = access_token
        self._http = httpx.AsyncClient(
            base_url=base_url,
            timeout=20.0,
            transport=transport,
            headers={
                "access-token": access_token,
                "client-id": client_id,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        self._quote_lock = asyncio.Lock()
        self._last_quote = 0.0

    async def close(self) -> None:
        await self._http.aclose()

    async def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        body = None
        if payload is not None:
            body = {**payload, "dhanClientId": self.client_id}
        try:
            r = await self._http.request(method, path, json=body)
        except httpx.HTTPError as exc:
            raise DhanError(f"Cannot reach Dhan: {type(exc).__name__}") from exc
        try:
            data = r.json() if r.content else {}
        except ValueError:
            data = {"errorMessage": r.text[:200]}
        if r.is_success:
            return data
        code = data.get("errorCode") if isinstance(data, dict) else None
        msg = (data.get("errorMessage") if isinstance(data, dict) else None) or r.reason_phrase
        if r.status_code == 401 or code in ("DH-901", "DH-902"):
            raise DhanAuthError(
                f"Dhan rejected the access token ({code or r.status_code}): {msg}. "
                "Generate a new token on web.dhan.co and save it in Settings."
            )
        raise DhanError(f"Dhan error {code or r.status_code}: {msg}")

    # ---------------------------------------------------------------- account
    async def profile(self) -> dict[str, Any]:
        return dict(await self.request("GET", "/profile"))

    async def fund_limit(self) -> dict[str, Any]:
        return dict(await self.request("GET", "/fundlimit"))

    async def positions(self) -> list[dict[str, Any]]:
        return list(await self.request("GET", "/positions") or [])

    async def orders(self) -> list[dict[str, Any]]:
        return list(await self.request("GET", "/orders") or [])

    async def renew_token(self) -> str:
        """Extend the current token by 24 h. Returns the new token."""
        try:
            r = await self._http.get("/RenewToken", headers={"dhanClientId": self.client_id})
        except httpx.HTTPError as exc:
            raise DhanError(f"Cannot reach Dhan: {type(exc).__name__}") from exc
        data = r.json() if r.content else {}
        token = data.get("token") or data.get("accessToken") if isinstance(data, dict) else None
        if not r.is_success or not token:
            raise DhanAuthError(f"Dhan did not renew the token: {data or r.status_code}")
        self.access_token = str(token)
        self._http.headers["access-token"] = self.access_token
        return self.access_token

    # ----------------------------------------------------------------- orders
    async def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        return dict(await self.request("POST", "/orders", payload))

    async def modify_order(self, order_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return dict(
            await self.request("PUT", f"/orders/{order_id}", {"orderId": order_id, **payload})
        )

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        return dict(await self.request("DELETE", f"/orders/{order_id}"))

    async def order(self, order_id: str) -> dict[str, Any]:
        data = await self.request("GET", f"/orders/{order_id}")
        return dict(data[0] if isinstance(data, list) and data else data)

    async def place_super_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Entry + target + stop-loss (+ trailing jump) held at Dhan."""
        return dict(await self.request("POST", "/super/orders", payload))

    async def modify_super_order(self, order_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = {"orderId": order_id, **payload}
        return dict(await self.request("PUT", f"/super/orders/{order_id}", body))

    async def cancel_super_order(self, order_id: str, leg: str = "ENTRY_LEG") -> dict[str, Any]:
        return dict(await self.request("DELETE", f"/super/orders/{order_id}/{leg}"))

    async def exit_all(self) -> dict[str, Any]:
        """Exit every position and cancel every open order for the day."""
        return dict(await self.request("DELETE", "/positions") or {})

    async def kill_switch(self, activate: bool) -> dict[str, Any]:
        state = "ACTIVATE" if activate else "DEACTIVATE"
        return dict(await self.request("POST", f"/killswitch?killSwitchStatus={state}", {}))

    # ------------------------------------------------------------- market data
    async def ltp(self, by_segment: dict[str, list[int]]) -> dict[str, dict[str, Any]]:
        async with self._quote_lock:
            wait = self.MIN_QUOTE_INTERVAL - (time.monotonic() - self._last_quote)
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                data = await self.request("POST", "/marketfeed/ltp", dict(by_segment))
            finally:
                self._last_quote = time.monotonic()
        return dict((data or {}).get("data") or {})

    async def intraday(
        self,
        security_id: str,
        segment: str,
        instrument: str,
        day_from: date,
        day_to: date,
        interval: int = 1,
    ) -> dict[str, list[Any]]:
        payload = {
            "securityId": security_id,
            "exchangeSegment": segment,
            "instrument": instrument,
            "interval": interval,
            "oi": False,
            "fromDate": day_from.isoformat(),
            "toDate": day_to.isoformat(),
        }
        return dict(await self.request("POST", "/charts/intraday", payload) or {})

    async def rolling_option(
        self,
        underlying_id: str,
        segment: str,
        instrument: str,
        expiry_flag: str,
        expiry_code: int,
        strike: str,
        option_type: str,
        day_from: date,
        day_to: date,
        interval: int = 1,
    ) -> dict[str, Any]:
        """Expired-option minute data relative to ATM (strike "ATM", "ATM+1", ...)."""
        payload = {
            "securityId": underlying_id,
            "exchangeSegment": segment,
            "instrument": instrument,
            "expiryFlag": expiry_flag,
            "expiryCode": expiry_code,
            "strike": strike,
            "drvOptionType": option_type,
            "requiredData": ["open", "high", "low", "close", "volume", "strike"],
            "fromDate": day_from.isoformat(),
            "toDate": day_to.isoformat(),
            "interval": interval,
        }
        return dict(await self.request("POST", "/charts/rollingoption", payload) or {})


class DhanBrokerAdapter(BrokerAdapter):
    name = "dhan"
    mode = ExecutionMode.LIVE

    def __init__(self, client: DhanClient) -> None:
        self.client = client

    async def health(self) -> AdapterHealth:
        try:
            p = await self.client.profile()
        except MarketOSError as exc:
            return AdapterHealth(name=self.name, state=AdapterState.ERROR, detail=exc.message)
        return AdapterHealth(
            name=self.name,
            state=AdapterState.READY,
            detail=f"Connected as {p.get('dhanClientId', '?')}",
        )

    async def profile(self) -> BrokerProfile:
        p = await self.client.profile()
        detail = {
            k: str(p[k])
            for k in ("tokenValidity", "activeSegment", "dataPlan", "dataValidity", "ddpi")
            if p.get(k) is not None
        }
        return BrokerProfile(user_id=str(p.get("dhanClientId", "")), detail=detail)

    async def funds(self) -> BrokerFunds:
        f = await self.client.fund_limit()
        # (sic) Dhan spells it "availabelBalance"
        avail = f.get("availabelBalance", f.get("availableBalance", 0))
        return BrokerFunds(
            available=_dec(avail),
            used=_dec(f.get("utilizedAmount", 0)),
            detail={
                k: str(f[k])
                for k in ("sodLimit", "collateralAmount", "withdrawableBalance")
                if f.get(k) is not None
            },
        )

    async def get_positions(self) -> list[BrokerPosition]:
        out: list[BrokerPosition] = []
        for p in await self.client.positions():
            ex = _EXCHANGE.get(str(p.get("exchangeSegment")))
            if ex is None:
                continue
            out.append(
                BrokerPosition(
                    exchange=ex,
                    tradingsymbol=str(p.get("tradingSymbol", "")),
                    product=_PRODUCT_BACK.get(str(p.get("productType")), ProductType.NRML),
                    quantity=int(p.get("netQty") or 0),
                    average_price=_dec(p.get("costPrice") or p.get("buyAvg") or 0),
                )
            )
        return out

    def order_payload(self, req: BrokerOrderRequest) -> dict[str, Any]:
        if not req.security_id:
            raise InvalidInputError(
                f"No Dhan security id for {req.tradingsymbol}; sync Dhan instruments first."
            )
        return {
            "transactionType": "BUY" if req.side is Side.BUY else "SELL",
            "exchangeSegment": _SEGMENT[req.exchange],
            "productType": _PRODUCT[req.product],
            "orderType": _ORDER_TYPE[req.order_type],
            "validity": req.validity.value,
            "securityId": req.security_id,
            "quantity": req.quantity,
            "disclosedQuantity": 0,
            "price": float(req.price or 0),
            "triggerPrice": float(req.trigger_price or 0),
            "afterMarketOrder": False,
            "correlationId": req.client_order_id[:25],
        }

    async def place_order(self, request: BrokerOrderRequest) -> BrokerOrderAck:
        data = await self.client.place_order(self.order_payload(request))
        return BrokerOrderAck(
            client_order_id=request.client_order_id,
            broker_order_id=str(data.get("orderId", "")),
            status=_STATUS.get(str(data.get("orderStatus")), OrderStatus.SUBMITTED),
        )

    async def place_super_order(
        self,
        request: BrokerOrderRequest,
        target: Decimal,
        stop_loss: Decimal,
        trailing_jump: Decimal = Decimal("0"),
    ) -> BrokerOrderAck:
        payload = self.order_payload(request)
        body = {
            k: payload[k]
            for k in (
                "transactionType",
                "exchangeSegment",
                "productType",
                "orderType",
                "securityId",
                "quantity",
                "price",
                "correlationId",
            )
        }
        body.update(
            targetPrice=float(target),
            stopLossPrice=float(stop_loss),
            trailingJump=float(trailing_jump),
        )
        data = await self.client.place_super_order(body)
        return BrokerOrderAck(
            client_order_id=request.client_order_id,
            broker_order_id=str(data.get("orderId", "")),
            status=_STATUS.get(str(data.get("orderStatus")), OrderStatus.SUBMITTED),
        )

    async def modify_super_stop(
        self, order_id: str, stop_loss: Decimal, trailing_jump: Decimal = Decimal("0")
    ) -> None:
        await self.client.modify_super_order(
            order_id,
            {
                "legName": "STOP_LOSS_LEG",
                "stopLossPrice": float(stop_loss),
                "trailingJump": float(trailing_jump),
            },
        )

    async def modify_order(self, broker_order_id: str, change: BrokerOrderChange) -> None:
        current = await self.client.order(broker_order_id)
        payload = {
            "orderType": _ORDER_TYPE[change.order_type]
            if change.order_type
            else current.get("orderType"),
            "legName": current.get("legName") or "",
            "quantity": change.quantity or current.get("quantity"),
            "price": float(change.price if change.price is not None else current.get("price", 0)),
            "triggerPrice": float(
                change.trigger_price
                if change.trigger_price is not None
                else current.get("triggerPrice", 0)
            ),
            "disclosedQuantity": 0,
            "validity": current.get("validity") or "DAY",
        }
        await self.client.modify_order(broker_order_id, payload)

    async def cancel_order(self, broker_order_id: str) -> BrokerOrderUpdate:
        data = await self.client.cancel_order(broker_order_id)
        return BrokerOrderUpdate(
            broker_order_id=broker_order_id,
            status=_STATUS.get(str(data.get("orderStatus")), OrderStatus.CANCELLED),
        )

    async def get_order(self, broker_order_id: str) -> BrokerOrderUpdate:
        o = await self.client.order(broker_order_id)
        return BrokerOrderUpdate(
            broker_order_id=broker_order_id,
            status=_STATUS.get(str(o.get("orderStatus")), OrderStatus.OPEN),
            filled_quantity=int(o.get("filledQty") or 0),
            average_price=_dec(o["averageTradedPrice"]) if o.get("averageTradedPrice") else None,
            message=o.get("omsErrorDescription") or None,
        )

    async def exit_all(self) -> None:
        await self.client.exit_all()

    async def set_kill_switch(self, on: bool) -> None:
        await self.client.kill_switch(on)


def epoch_to_utc(ts: float | int) -> datetime:
    return datetime.fromtimestamp(float(ts), UTC)

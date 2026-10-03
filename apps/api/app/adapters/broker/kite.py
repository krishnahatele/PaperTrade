"""Zerodha Kite Connect broker adapter (the official client is synchronous, so
calls run in a worker thread). Kite has no bracket/trailing orders: MarketOS
keeps the stop-loss and targets itself and modifies them as needed."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from decimal import Decimal
from typing import Any, TypeVar

from kiteconnect import KiteConnect
from kiteconnect import exceptions as kex

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
from app.core.errors import MarketOSError
from app.models.enums import Exchange, ExecutionMode, OrderStatus, ProductType, Side

T = TypeVar("T")

_STATUS = {
    "OPEN": OrderStatus.OPEN,
    "TRIGGER PENDING": OrderStatus.OPEN,
    "COMPLETE": OrderStatus.FILLED,
    "CANCELLED": OrderStatus.CANCELLED,
    "REJECTED": OrderStatus.REJECTED,
}


class KiteBrokerError(MarketOSError):
    status_code = 502
    code = "kite_error"


class KiteBrokerAdapter(BrokerAdapter):
    name = "kite"
    mode = ExecutionMode.LIVE

    def __init__(self, api_key: str, access_token: str, kite: Any | None = None) -> None:
        self._kite = kite or KiteConnect(api_key=api_key, access_token=access_token, timeout=15)

    async def _call(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        except kex.TokenException as exc:
            raise KiteBrokerError("Kite session expired. Log in to Kite again.") from exc
        except kex.KiteException as exc:
            raise KiteBrokerError(f"Kite error: {exc}") from exc

    async def health(self) -> AdapterHealth:
        try:
            p = await self.profile()
        except MarketOSError as exc:
            return AdapterHealth(name=self.name, state=AdapterState.ERROR, detail=exc.message)
        return AdapterHealth(
            name=self.name, state=AdapterState.READY, detail=f"Connected as {p.user_id}"
        )

    async def profile(self) -> BrokerProfile:
        p = await self._call(self._kite.profile)
        return BrokerProfile(
            user_id=str(p.get("user_id", "")),
            name=p.get("user_name"),
            detail={"broker": str(p.get("broker", "ZERODHA"))},
        )

    async def funds(self) -> BrokerFunds:
        m = await self._call(self._kite.margins, "equity")
        avail = (m.get("available") or {}).get("live_balance", m.get("net", 0))
        used = (m.get("utilised") or {}).get("debits", 0)
        return BrokerFunds(available=Decimal(str(avail)), used=Decimal(str(used)))

    async def get_positions(self) -> list[BrokerPosition]:
        data = await self._call(self._kite.positions)
        out = []
        for p in data.get("net", []):
            try:
                ex = Exchange(p["exchange"])
                product = ProductType(p["product"])
            except (KeyError, ValueError):
                continue
            out.append(
                BrokerPosition(
                    exchange=ex,
                    tradingsymbol=p["tradingsymbol"],
                    product=product,
                    quantity=int(p.get("quantity") or 0),
                    average_price=Decimal(str(p.get("average_price") or 0)),
                )
            )
        return out

    async def place_order(self, request: BrokerOrderRequest) -> BrokerOrderAck:
        oid = await self._call(
            self._kite.place_order,
            variety="regular",
            exchange=request.exchange.value,
            tradingsymbol=request.tradingsymbol,
            transaction_type="BUY" if request.side is Side.BUY else "SELL",
            quantity=request.quantity,
            product=request.product.value,
            order_type=request.order_type.value,
            price=float(request.price) if request.price is not None else None,
            trigger_price=float(request.trigger_price) if request.trigger_price else None,
            validity=request.validity.value,
            tag=request.client_order_id[:20],
        )
        return BrokerOrderAck(
            client_order_id=request.client_order_id,
            broker_order_id=str(oid),
            status=OrderStatus.SUBMITTED,
        )

    async def modify_order(self, broker_order_id: str, change: BrokerOrderChange) -> None:
        await self._call(
            self._kite.modify_order,
            variety="regular",
            order_id=broker_order_id,
            quantity=change.quantity,
            price=float(change.price) if change.price is not None else None,
            trigger_price=float(change.trigger_price) if change.trigger_price else None,
            order_type=change.order_type.value if change.order_type else None,
        )

    async def cancel_order(self, broker_order_id: str) -> BrokerOrderUpdate:
        await self._call(self._kite.cancel_order, variety="regular", order_id=broker_order_id)
        return BrokerOrderUpdate(broker_order_id=broker_order_id, status=OrderStatus.CANCELLED)

    async def get_order(self, broker_order_id: str) -> BrokerOrderUpdate:
        history = await self._call(self._kite.order_history, broker_order_id)
        last = history[-1] if history else {}
        return BrokerOrderUpdate(
            broker_order_id=broker_order_id,
            status=_STATUS.get(str(last.get("status")), OrderStatus.SUBMITTED),
            filled_quantity=int(last.get("filled_quantity") or 0),
            average_price=Decimal(str(last["average_price"]))
            if last.get("average_price")
            else None,
            message=last.get("status_message"),
        )

    async def exit_all(self) -> None:
        """Kite has no single call: square off each open position at market."""
        for p in await self.get_positions():
            if p.quantity == 0:
                continue
            await self._call(
                self._kite.place_order,
                variety="regular",
                exchange=p.exchange.value,
                tradingsymbol=p.tradingsymbol,
                transaction_type="SELL" if p.quantity > 0 else "BUY",
                quantity=abs(p.quantity),
                product=p.product.value,
                order_type="MARKET",
                tag="mos-exit-all",
            )

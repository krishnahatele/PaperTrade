from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.api.deps import ContainerDep, SessionDep
from app.events import Event, EventType
from app.models import Instrument
from app.schemas.trading import KiteSessionBody, LtpRead, ManualPriceBody
from app.services.kite import KiteStatus
from app.services.repository import Repository

router = APIRouter(tags=["market data"])


@router.get("/kite/status", response_model=KiteStatus)
async def kite_status(container: ContainerDep) -> KiteStatus:
    return await container.kite.status()


@router.get(
    "/kite/login-url", summary="Open this URL, log in to Zerodha, then paste the redirect URL back"
)
async def kite_login_url(container: ContainerDep) -> dict[str, str]:
    return {"url": await container.kite.login_url()}


@router.post(
    "/kite/session", response_model=KiteStatus, summary="Exchange request_token for today's session"
)
async def kite_session(body: KiteSessionBody, container: ContainerDep) -> KiteStatus:
    st = await container.kite.create_session(body.request_token)
    await container.market.reload()
    return st


@router.post("/kite/logout", status_code=status.HTTP_204_NO_CONTENT)
async def kite_logout(container: ContainerDep) -> None:
    await container.kite.logout()
    await container.market.reload()


@router.get("/market/ltp", response_model=list[LtpRead])
async def ltp(
    session: SessionDep, container: ContainerDep, instrument_id: list[uuid.UUID] = Query(...)
) -> list[LtpRead]:
    insts = list(await session.scalars(select(Instrument).where(Instrument.id.in_(instrument_id))))
    prices = await container.market.ltp(insts)
    return [
        LtpRead(instrument_id=i.id, tradingsymbol=i.tradingsymbol, ltp=prices.get(i.id))
        for i in insts
    ]


@router.post(
    "/market/manual-price",
    response_model=LtpRead,
    summary="Set a price by hand (used when Kite has no live price, e.g. for practice)",
)
async def manual_price(
    body: ManualPriceBody, session: SessionDep, container: ContainerDep
) -> LtpRead:
    inst = await Repository(session, Instrument).get(body.instrument_id)
    container.market.set_manual(inst.id, body.price)
    await container.bus.publish(
        Event(
            type=EventType.MANUAL_PRICE_SET,
            aggregate_type="instrument",
            aggregate_id=inst.id,
            payload={"price": str(body.price)},
        )
    )
    await container.engine.tick()
    return LtpRead(instrument_id=inst.id, tradingsymbol=inst.tradingsymbol, ltp=body.price)

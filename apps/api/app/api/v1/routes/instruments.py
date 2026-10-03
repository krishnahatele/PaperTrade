from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status
from pydantic import BaseModel

from app.api.deps import BusDep, ContainerDep, PageDep, SessionDep
from app.models import Instrument
from app.models.enums import Exchange
from app.schemas.common import Page
from app.schemas.instrument import InstrumentCreate, InstrumentRead
from app.services.catalog import InstrumentService
from app.services.repository import Repository

router = APIRouter(prefix="/instruments", tags=["instruments"])


@router.get("", response_model=Page[InstrumentRead])
async def list_instruments(
    session: SessionDep,
    page: PageDep,
    exchange: Exchange | None = None,
    q: str | None = Query(default=None, max_length=64, description="Symbol prefix search"),
) -> Page[InstrumentRead]:
    filters = []
    if exchange is not None:
        filters.append(Instrument.exchange == exchange)
    if q:
        filters.append(Instrument.tradingsymbol.ilike(f"{q}%"))
    rows, total = await Repository(session, Instrument).list(
        filters=filters,
        order_by=[Instrument.exchange, Instrument.tradingsymbol],
        limit=page.limit,
        offset=page.offset,
    )
    return Page(
        items=[InstrumentRead.model_validate(r) for r in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{instrument_id}", response_model=InstrumentRead)
async def get_instrument(instrument_id: uuid.UUID, session: SessionDep) -> Instrument:
    return await Repository(session, Instrument).get(instrument_id)


@router.post("", response_model=InstrumentRead, status_code=status.HTTP_201_CREATED)
async def create_instrument(data: InstrumentCreate, session: SessionDep, bus: BusDep) -> Instrument:
    return await InstrumentService(session, bus).create(data)


class SyncBody(BaseModel):
    exchanges: list[Exchange] = [Exchange.NSE, Exchange.NFO]


@router.post(
    "/sync",
    response_model=dict[str, int],
    summary="Download the instrument list from Kite (public, no login needed)",
)
async def sync_instruments(container: ContainerDep, body: SyncBody | None = None) -> dict[str, int]:
    return await container.instruments.sync((body or SyncBody()).exchanges)

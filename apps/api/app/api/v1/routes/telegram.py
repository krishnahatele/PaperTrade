from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.api.deps import BusDep, ContainerDep, SessionDep
from app.models import SignalSource
from app.models.enums import SignalSourceKind
from app.schemas.signal_source import SignalSourceCreate, SignalSourceRead
from app.schemas.telegram import (
    AddChannelBody,
    BackfillResponse,
    ChannelRead,
    CodeBody,
    LoginStepResponse,
    PasswordBody,
)
from app.services.catalog import SignalSourceService
from app.services.telegram import TelegramStatus

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.get("/status", response_model=TelegramStatus)
async def telegram_status(container: ContainerDep) -> TelegramStatus:
    return await container.telegram.status()


@router.post(
    "/login/start",
    response_model=LoginStepResponse,
    summary="Send a login code to the saved phone number",
)
async def login_start(container: ContainerDep) -> LoginStepResponse:
    return LoginStepResponse(step=await container.telegram.begin_login())


@router.post("/login/code", response_model=LoginStepResponse)
async def login_code(body: CodeBody, container: ContainerDep) -> LoginStepResponse:
    return LoginStepResponse(step=await container.telegram.submit_code(body.code))


@router.post(
    "/login/password",
    response_model=LoginStepResponse,
    summary="Two-step verification password",
)
async def login_password(body: PasswordBody, container: ContainerDep) -> LoginStepResponse:
    return LoginStepResponse(step=await container.telegram.submit_password(body.password))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(container: ContainerDep) -> None:
    await container.telegram.logout()


@router.get("/channels", response_model=list[ChannelRead], summary="Channels/groups you belong to")
async def channels(container: ContainerDep, session: SessionDep) -> list[ChannelRead]:
    found = await container.telegram.list_channels()
    rows = await session.scalars(
        select(SignalSource).where(SignalSource.kind == SignalSourceKind.TELEGRAM)
    )
    by_ext = {s.external_id: s for s in rows}
    out = []
    for c in found:
        src = by_ext.get(c.id)
        out.append(
            ChannelRead(
                **c.model_dump(),
                source_id=str(src.id) if src else None,
                source_enabled=src.is_enabled if src else None,
            )
        )
    return out


@router.post(
    "/channels",
    response_model=SignalSourceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a channel as a signal source",
)
async def add_channel(
    body: AddChannelBody, container: ContainerDep, session: SessionDep, bus: BusDep
) -> SignalSource:
    src = await SignalSourceService(session, bus).create(
        SignalSourceCreate(
            kind=SignalSourceKind.TELEGRAM,
            name=body.name,
            external_id=body.channel_id,
            is_enabled=body.enabled,
        )
    )
    await container.telegram.start_listening()
    return src


@router.post("/sources/{source_id}/backfill", response_model=BackfillResponse)
async def backfill(
    source_id: uuid.UUID,
    container: ContainerDep,
    limit: int = Query(default=50, ge=1, le=500),
) -> BackfillResponse:
    return BackfillResponse(stored=await container.telegram.backfill(source_id, limit))

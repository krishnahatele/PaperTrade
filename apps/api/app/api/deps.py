"""FastAPI dependency providers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.container import Container
from app.events import EventBus
from app.schemas.common import PageParams


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


async def get_session(container: ContainerDep) -> AsyncIterator[AsyncSession]:
    async with container.db.session_factory() as session:
        yield session


def get_bus(container: ContainerDep) -> EventBus:
    return container.bus


SessionDep = Annotated[AsyncSession, Depends(get_session)]
BusDep = Annotated[EventBus, Depends(get_bus)]
PageDep = Annotated[PageParams, Depends()]

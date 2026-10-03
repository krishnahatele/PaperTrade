"""FastAPI dependency providers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.container import Container
from app.events import EventBus
from app.schemas.common import PageParams
from app.services.auth import AuthError


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


_bearer = HTTPBearer(auto_error=False)


async def require_auth(
    container: ContainerDep,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> None:
    """Protects every /api/v1 route except /auth/*."""
    if not container.settings.auth_enabled:
        return
    if creds is None or not await container.auth().verify(creds.credentials):
        raise AuthError("Authentication required.")

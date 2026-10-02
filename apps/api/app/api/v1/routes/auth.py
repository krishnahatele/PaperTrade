from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.deps import ContainerDep
from app.schemas.auth import AuthStatus, ChangePasswordBody, PasswordBody, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)


@router.get("/status", response_model=AuthStatus)
async def auth_status(
    container: ContainerDep,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthStatus:
    auth = container.auth()
    enabled = container.settings.auth_enabled
    authed = (not enabled) or (creds is not None and await auth.verify(creds.credentials))
    return AuthStatus(
        auth_enabled=enabled, configured=await auth.is_configured(), authenticated=authed
    )


@router.post("/setup", response_model=TokenResponse, summary="Set the admin password (first run)")
async def setup(body: PasswordBody, container: ContainerDep) -> TokenResponse:
    token, exp = await container.auth().setup(body.password)
    return TokenResponse(token=token, expires_at=exp)


@router.post("/login", response_model=TokenResponse)
async def login(body: PasswordBody, container: ContainerDep) -> TokenResponse:
    token, exp = await container.auth().login(body.password)
    return TokenResponse(token=token, expires_at=exp)


@router.post(
    "/change-password",
    response_model=TokenResponse,
    summary="Change password and revoke all existing tokens",
)
async def change_password(body: ChangePasswordBody, container: ContainerDep) -> TokenResponse:
    token, exp = await container.auth().change_password(body.current_password, body.new_password)
    return TokenResponse(token=token, expires_at=exp)

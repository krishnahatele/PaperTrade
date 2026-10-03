from __future__ import annotations

from pydantic import BaseModel, Field


class AuthStatus(BaseModel):
    auth_enabled: bool
    configured: bool
    authenticated: bool


class PasswordBody(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordBody(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    token: str
    expires_at: int

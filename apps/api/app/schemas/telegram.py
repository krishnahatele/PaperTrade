from __future__ import annotations

from pydantic import BaseModel, Field

from app.adapters.telegram import LoginStep


class LoginStepResponse(BaseModel):
    step: LoginStep


class CodeBody(BaseModel):
    code: str = Field(min_length=3, max_length=12, pattern=r"^[0-9 ]+$")


class PasswordBody(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class ChannelRead(BaseModel):
    id: str
    title: str
    username: str | None
    kind: str
    source_id: str | None = None
    source_enabled: bool | None = None


class AddChannelBody(BaseModel):
    channel_id: str = Field(pattern=r"^-?\d+$")
    name: str = Field(min_length=1, max_length=128)
    enabled: bool = True


class BackfillResponse(BaseModel):
    stored: int

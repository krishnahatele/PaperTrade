from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import SignalSourceKind
from app.schemas.common import ReadModel


class SignalSourceBase(BaseModel):
    kind: SignalSourceKind
    name: str = Field(min_length=1, max_length=128)
    external_id: str | None = Field(default=None, max_length=128)
    is_enabled: bool = False
    config: dict[str, Any] = Field(default_factory=dict)


class SignalSourceCreate(SignalSourceBase):
    pass


class SignalSourceRead(SignalSourceBase, ReadModel):
    pass


class SignalSourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    is_enabled: bool | None = None
    config: dict[str, Any] | None = None

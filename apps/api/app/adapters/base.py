"""Common adapter contract."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel


class AdapterState(StrEnum):
    READY = "ready"
    DISABLED = "disabled"
    NOT_CONFIGURED = "not_configured"
    ERROR = "error"


class AdapterHealth(BaseModel):
    name: str
    state: AdapterState
    detail: str | None = None


class Adapter(Protocol):
    """Every external integration exposes a name and a health probe."""

    name: str

    async def health(self) -> AdapterHealth: ...

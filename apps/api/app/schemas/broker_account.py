from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import BrokerName, ExecutionMode
from app.schemas.common import ReadModel


class BrokerAccountBase(BaseModel):
    broker: BrokerName
    label: str = Field(min_length=1, max_length=128)
    external_account_id: str | None = Field(default=None, max_length=64)
    credentials_ref: str | None = Field(
        default=None,
        max_length=255,
        description="Reference to a secret (env var / vault path). Never the secret itself.",
    )
    is_active: bool = True
    settings: dict[str, Any] = Field(default_factory=dict)


class BrokerAccountCreate(BrokerAccountBase):
    mode: ExecutionMode = ExecutionMode.PAPER


class BrokerAccountRead(BrokerAccountBase, ReadModel):
    mode: ExecutionMode


class BrokerAccountUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=128)
    is_active: bool | None = None
    settings: dict[str, Any] | None = Field(
        default=None, description="Risk settings; see AccountRiskSettings for fields"
    )

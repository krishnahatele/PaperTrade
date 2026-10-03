from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.adapters.llm.providers import LLMProvider
from app.services.runtime import ParsingRuntime, TradingRuntime


def mask(value: str | None, keep: int = 4) -> str | None:
    if not value:
        return None
    return "•" * min(max(len(value) - keep, 4), 8) + value[-keep:]


class SecretField(BaseModel):
    set: bool
    hint: str | None = Field(default=None, description="Masked preview, e.g. ••••1234")


class TelegramCredentials(BaseModel):
    api_id: str | None = Field(default=None, pattern=r"^\d{3,12}$")
    api_hash: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{32}$")
    phone: str | None = Field(
        default=None,
        pattern=r"^\+\d{7,15}$",
        description="International format, e.g. +919876543210",
    )


class KiteCredentials(BaseModel):
    api_key: str | None = Field(default=None, min_length=4, max_length=64)
    api_secret: str | None = Field(default=None, min_length=4, max_length=128)


class LLMCredentials(BaseModel):
    provider: LLMProvider | None = Field(default=None, description="Defaults to the active one")
    api_key: str | None = Field(default=None, min_length=8, max_length=256)

    @field_validator("api_key")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return v.strip() if v else v


class TelegramStatus(BaseModel):
    api_id: SecretField
    api_hash: SecretField
    phone: SecretField
    authorized: bool


class KiteStatus(BaseModel):
    api_key: SecretField
    api_secret: SecretField
    session_active: bool
    user_id: str | None


class LLMStatus(BaseModel):
    provider: LLMProvider
    model: str
    api_key: SecretField


class IntegrationsStatus(BaseModel):
    telegram: TelegramStatus
    kite: KiteStatus
    llm: LLMStatus


class RuntimeSettingsRead(BaseModel):
    trading: TradingRuntime
    parsing: ParsingRuntime

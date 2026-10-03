"""Runtime settings editable from the UI, persisted in ``app_settings``."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Any, TypeVar

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import AppSetting


class ParserMode(StrEnum):
    RULES_ONLY = "rules_only"
    RULES_THEN_LLM = "rules_then_llm"
    LLM_ONLY = "llm_only"


class TradingRuntime(BaseModel):
    """Global trading controls."""

    kill_switch: bool = Field(
        default=False, description="When on, no new orders are placed anywhere."
    )
    auto_execute: bool = Field(
        default=False, description="Automatically execute validated signals (paper accounts)."
    )
    live_armed: bool = Field(
        default=False,
        description="Second, runtime switch for live trading. Requires the env flag as well.",
    )
    min_confidence: Decimal = Field(default=Decimal("0.6"), ge=0, le=1)
    signal_ttl_minutes: int = Field(default=30, gt=0, le=24 * 60)


class ParsingRuntime(BaseModel):
    mode: ParserMode = ParserMode.RULES_THEN_LLM
    llm_model: str = "claude-opus-5-5"
    llm_provider: str = "anthropic"


class AuthRuntime(BaseModel):
    token_generation: int = 0


M = TypeVar("M", bound=BaseModel)

_KEYS: dict[type[BaseModel], str] = {
    TradingRuntime: "trading",
    ParsingRuntime: "parsing",
    AuthRuntime: "auth",
}


class RuntimeStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def get(self, model: type[M]) -> M:
        async with self._sf() as s:
            rec = await s.get(AppSetting, _KEYS[model])
            return model.model_validate(rec.value if rec else {})

    async def update(self, model: type[M], **changes: Any) -> M:
        async with self._sf() as s:
            key = _KEYS[model]
            rec = await s.get(AppSetting, key)
            current = model.model_validate(rec.value if rec else {})
            updated = model.model_validate({**current.model_dump(), **changes})
            value = updated.model_dump(mode="json")
            if rec is None:
                s.add(AppSetting(key=key, value=value))
            else:
                rec.value = value
            await s.commit()
            return updated

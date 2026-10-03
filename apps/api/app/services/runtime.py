"""Runtime settings editable from the UI, persisted in ``app_settings``."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, TypeVar

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.broker.providers import BrokerProvider
from app.adapters.llm.providers import LLMProvider
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
    llm_provider: LLMProvider = LLMProvider.ANTHROPIC
    llm_model: str = Field(default="claude-haiku-4-5", min_length=1, max_length=200)
    # Only used by the custom / Ollama providers (others have a fixed URL).
    llm_base_url: str | None = Field(default=None, max_length=500)


class DataSource(StrEnum):
    AUTO = "auto"  # Kite if logged in, else Dhan
    KITE = "kite"
    DHAN = "dhan"
    MANUAL = "manual"  # practice prices typed in by hand


class BrokerRuntime(BaseModel):
    # The broker you trade with. Orders stay paper in this build; this picks
    # whose positions/funds are shown and where live orders would go later.
    primary: BrokerProvider = BrokerProvider.PAPER
    market_data: DataSource = DataSource.AUTO
    history: DataSource = DataSource.AUTO
    dhan_token_saved_at: datetime | None = None


class BotNotify(BaseModel):
    signals: bool = True  # new signals / waiting trades with Buy now / Cancel
    trades: bool = True  # fills, targets, stops, closes
    skipped: bool = True  # signals not taken (risk rules, kill switch, ...)
    news: bool = True
    market_moves: bool = True


class BotRuntime(BaseModel):
    """The private Telegram control bot (its token is in the secret store)."""

    owner_chat_id: int | None = None
    owner_name: str | None = None
    username: str | None = None
    link_code: str | None = None
    link_expires_at: datetime | None = None
    pinned_message_id: int | None = None
    notify: BotNotify = Field(default_factory=BotNotify)


class AuthRuntime(BaseModel):
    token_generation: int = 0


M = TypeVar("M", bound=BaseModel)

_KEYS: dict[type[BaseModel], str] = {
    TradingRuntime: "trading",
    ParsingRuntime: "parsing",
    AuthRuntime: "auth",
    BrokerRuntime: "broker",
    BotRuntime: "bot",
}


def register_runtime(model: type[BaseModel], key: str) -> None:
    """Let a feature module keep its own settings model (avoids import cycles)."""
    _KEYS[model] = key


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

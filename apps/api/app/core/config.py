"""Typed application configuration.

All settings are read from environment variables (prefix ``MARKETOS_``) or a
``.env`` file. Nothing else in the codebase should read ``os.environ`` directly.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, PostgresDsn, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class TradingMode(StrEnum):
    """Global execution mode. Phase 0 only permits ``disabled`` and ``paper``."""

    DISABLED = "disabled"
    PAPER = "paper"
    LIVE = "live"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MARKETOS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application -------------------------------------------------------
    app_name: str = "MarketOS"
    environment: Environment = Environment.LOCAL
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Start long-running integrations (Telegram listener, market data, ...)
    # on startup. Disabled in tests.
    background_services: bool = True

    # --- Logging -----------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = True

    # --- Database ----------------------------------------------------------
    database_url: PostgresDsn = PostgresDsn(
        "postgresql+asyncpg://marketos:marketos@localhost:5432/marketos"
    )
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_echo: bool = False

    # --- Security ----------------------------------------------------------
    # Master key (urlsafe base64, 32 bytes) used to encrypt stored credentials.
    # If unset, a key is generated once and kept in ``secret_key_file``.
    secret_key: SecretStr | None = None
    secret_key_file: str = ".secrets/master.key"  # noqa: S105 - a path, not a secret
    auth_enabled: bool = True
    auth_token_ttl_hours: int = Field(default=12, gt=0, le=24 * 30)

    # --- Trading safety ----------------------------------------------------
    # Live trading is hard-disabled until a later phase explicitly enables it.
    trading_mode: TradingMode = TradingMode.PAPER
    live_trading_enabled: bool = False

    # --- External integrations (placeholders; unused in Phase 0) ----------
    kite_api_key: SecretStr | None = None
    kite_api_secret: SecretStr | None = None
    telegram_api_id: SecretStr | None = None
    telegram_api_hash: SecretStr | None = None
    llm_provider: str = "none"
    llm_api_key: SecretStr | None = None

    @field_validator(
        "secret_key",
        "kite_api_key",
        "kite_api_secret",
        "telegram_api_id",
        "telegram_api_hash",
        "llm_api_key",
        mode="before",
    )
    @classmethod
    def _blank_is_none(cls, v: object) -> object:
        return None if isinstance(v, str) and not v.strip() else v

    @model_validator(mode="after")
    def _enforce_trading_safety(self) -> Settings:
        if self.trading_mode is TradingMode.LIVE or self.live_trading_enabled:
            raise ValueError(
                "Live trading is not available in this build (Phase 0). "
                "Set MARKETOS_TRADING_MODE to 'paper' or 'disabled' and "
                "MARKETOS_LIVE_TRADING_ENABLED=false."
            )
        return self

    @property
    def database_url_str(self) -> str:
        return str(self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()

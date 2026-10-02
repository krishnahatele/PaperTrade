from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.adapters.base import AdapterHealth
from app.core.config import Environment, TradingMode


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ComponentCheck(BaseModel):
    name: str
    ok: bool
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: Literal["ok", "degraded"]
    checks: list[ComponentCheck]


class SystemInfo(BaseModel):
    app_name: str
    version: str
    environment: Environment
    trading_mode: TradingMode
    live_trading_enabled: bool
    phase: str
    adapters: dict[str, AdapterHealth]

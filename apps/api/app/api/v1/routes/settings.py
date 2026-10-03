from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import ValidationError

from app.api.deps import ContainerDep
from app.core.errors import FeatureDisabledError, InvalidInputError
from app.events import Event, EventType
from app.schemas.integrations import RuntimeSettingsRead
from app.services.runtime import ParsingRuntime, TradingRuntime

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=RuntimeSettingsRead)
async def get_settings_(container: ContainerDep) -> RuntimeSettingsRead:
    return RuntimeSettingsRead(
        trading=await container.runtime.get(TradingRuntime),
        parsing=await container.runtime.get(ParsingRuntime),
    )


@router.patch("/trading", response_model=TradingRuntime)
async def patch_trading(changes: dict[str, Any], container: ContainerDep) -> TradingRuntime:
    allowed = {k: v for k, v in changes.items() if k in TradingRuntime.model_fields}
    if allowed.get("live_armed") and not container.settings.live_trading_enabled:
        raise FeatureDisabledError(
            "Live trading is disabled at the server level (MARKETOS_LIVE_TRADING_ENABLED=false)."
        )
    try:
        updated = await container.runtime.update(TradingRuntime, **allowed)
    except ValidationError as exc:
        raise InvalidInputError(str(exc.errors()[0]["msg"])) from exc
    await container.bus.publish(
        Event(
            type=EventType.SETTINGS_UPDATED,
            aggregate_type="settings",
            payload={
                "section": "trading",
                "changes": updated.model_dump(mode="json", include=set(allowed)),
            },
        )
    )
    return updated


@router.patch("/parsing", response_model=ParsingRuntime)
async def patch_parsing(changes: dict[str, Any], container: ContainerDep) -> ParsingRuntime:
    allowed = {k: v for k, v in changes.items() if k in ParsingRuntime.model_fields}
    try:
        updated = await container.runtime.update(ParsingRuntime, **allowed)
    except ValidationError as exc:
        raise InvalidInputError(str(exc.errors()[0]["msg"])) from exc
    await container.llm.reload()
    await container.bus.publish(
        Event(
            type=EventType.SETTINGS_UPDATED,
            aggregate_type="settings",
            payload={
                "section": "parsing",
                "changes": updated.model_dump(mode="json", include=set(allowed)),
            },
        )
    )
    return updated

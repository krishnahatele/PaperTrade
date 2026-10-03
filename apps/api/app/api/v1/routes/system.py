from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.api.deps import ContainerDep
from app.schemas.system import SystemInfo

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/info", response_model=SystemInfo, summary="Build, mode and adapter status")
async def info(container: ContainerDep) -> SystemInfo:
    s = container.settings
    return SystemInfo(
        app_name=s.app_name,
        version=__version__,
        environment=s.environment,
        trading_mode=s.trading_mode,
        live_trading_enabled=s.live_trading_enabled,
        phase="5",
        adapters=await container.adapters.health(),
    )

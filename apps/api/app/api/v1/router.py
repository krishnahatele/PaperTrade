from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import (
    broker_accounts,
    events,
    instruments,
    signal_sources,
    signals,
    system,
    trading,
)

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(instruments.router)
api_router.include_router(broker_accounts.router)
api_router.include_router(signal_sources.router)
api_router.include_router(signals.router)
api_router.include_router(trading.router)
api_router.include_router(events.router)

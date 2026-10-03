from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import require_auth
from app.api.v1.routes import (
    auth,
    bot,
    broker_accounts,
    brokers,
    events,
    instruments,
    integrations,
    llm,
    market,
    messages,
    news,
    settings,
    signal_sources,
    signals,
    system,
    telegram,
    trading,
)

api_router = APIRouter()
api_router.include_router(auth.router)

protected = APIRouter(dependencies=[Depends(require_auth)])
protected.include_router(system.router)
protected.include_router(instruments.router)
protected.include_router(broker_accounts.router)
protected.include_router(signal_sources.router)
protected.include_router(signals.router)
protected.include_router(trading.router)
protected.include_router(events.router)
protected.include_router(integrations.router)
protected.include_router(settings.router)
protected.include_router(telegram.router)
protected.include_router(messages.router)
protected.include_router(llm.router)
protected.include_router(market.router)
protected.include_router(brokers.router)
protected.include_router(bot.router)
protected.include_router(news.router)
api_router.include_router(protected)

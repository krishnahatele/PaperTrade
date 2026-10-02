"""FastAPI application factory and ASGI entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import health
from app.api.v1.router import api_router
from app.container import Container
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.events import Event, EventType

log = get_logger("marketos")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = Container.build(settings)
        app.state.container = container
        log.info(
            "app.startup",
            version=__version__,
            environment=settings.environment,
            trading_mode=settings.trading_mode,
        )
        await container.bus.publish(
            Event(type=EventType.SYSTEM_STARTED, payload={"version": __version__})
        )
        try:
            yield
        finally:
            await container.bus.publish(Event(type=EventType.SYSTEM_STOPPING))
            await container.close()
            log.info("app.shutdown")

    app = FastAPI(
        title=f"{settings.app_name} API",
        version=__version__,
        description=(
            "MarketOS backend. Phase 0: foundation only. "
            "No order placement, market data, Telegram ingestion or AI parsing."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()

"""Composition root: builds long-lived application dependencies once."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import Settings
from app.core.crypto import SecretBox, load_master_key
from app.db.session import Database
from app.events import InMemoryEventBus
from app.events.bus import WILDCARD
from app.events.store import EventStore
from app.services.adapters import AdapterRegistry
from app.services.auth import AuthService, LoginRateLimiter
from app.services.runtime import RuntimeStore
from app.services.secrets import SecretStore


@dataclass
class Container:
    settings: Settings
    db: Database
    bus: InMemoryEventBus
    box: SecretBox
    secrets: SecretStore
    runtime: RuntimeStore
    adapters: AdapterRegistry
    login_limiter: LoginRateLimiter = field(default_factory=LoginRateLimiter)

    @classmethod
    def build(cls, settings: Settings) -> Container:
        db = Database(settings)
        bus = InMemoryEventBus()
        bus.subscribe(WILDCARD, EventStore(db.session_factory))
        box = SecretBox(load_master_key(settings))
        return cls(
            settings=settings,
            db=db,
            bus=bus,
            box=box,
            secrets=SecretStore(db.session_factory, box),
            runtime=RuntimeStore(db.session_factory),
            adapters=AdapterRegistry.from_settings(settings),
        )

    def auth(self) -> AuthService:
        return AuthService(
            self.secrets,
            self.runtime,
            self.box,
            self.settings.auth_token_ttl_hours,
            self.login_limiter,
        )

    async def close(self) -> None:
        await self.db.dispose()

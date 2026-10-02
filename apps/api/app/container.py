"""Composition root: builds long-lived application dependencies once."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.db.session import Database
from app.events import InMemoryEventBus
from app.events.bus import WILDCARD
from app.events.store import EventStore
from app.services.adapters import AdapterRegistry


@dataclass
class Container:
    settings: Settings
    db: Database
    bus: InMemoryEventBus
    adapters: AdapterRegistry

    @classmethod
    def build(cls, settings: Settings) -> Container:
        db = Database(settings)
        bus = InMemoryEventBus()
        bus.subscribe(WILDCARD, EventStore(db.session_factory))
        return cls(
            settings=settings,
            db=db,
            bus=bus,
            adapters=AdapterRegistry.from_settings(settings),
        )

    async def close(self) -> None:
        await self.db.dispose()

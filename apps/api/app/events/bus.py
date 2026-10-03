"""In-process asynchronous event bus.

Phase 0 ships a single-process implementation. The ``EventBus`` protocol is the
seam for swapping in a durable broker (Redis Streams, NATS, Postgres
LISTEN/NOTIFY) later without touching publishers or subscribers.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Protocol

from app.core.logging import get_logger
from app.events.models import Event

EventHandler = Callable[[Event], Awaitable[None]]

WILDCARD = "*"

log = get_logger("marketos.events")


class EventBus(Protocol):
    def subscribe(self, event_type: str, handler: EventHandler) -> None: ...

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None: ...

    async def publish(self, event: Event) -> None: ...


class InMemoryEventBus:
    """Dispatches each event to all matching handlers concurrently.

    A failing handler is logged and isolated: it never prevents other handlers
    from running, and never propagates to the publisher.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        if handler in self._handlers.get(event_type, []):
            self._handlers[event_type].remove(handler)

    def handlers_for(self, event_type: str) -> list[EventHandler]:
        return [*self._handlers.get(event_type, []), *self._handlers.get(WILDCARD, [])]

    async def publish(self, event: Event) -> None:
        handlers = self.handlers_for(event.type)
        log.debug("event.published", event_type=event.type, event_id=str(event.id))
        if not handlers:
            return
        results = await asyncio.gather(*(h(event) for h in handlers), return_exceptions=True)
        for handler, result in zip(handlers, results, strict=True):
            if isinstance(result, BaseException):
                log.error(
                    "event.handler_failed",
                    event_type=event.type,
                    event_id=str(event.id),
                    handler=getattr(handler, "__qualname__", repr(handler)),
                    error=repr(result),
                )

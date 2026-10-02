"""Persists every published event to the ``events`` table."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.events.models import Event
from app.models.event import EventRecord


class EventStore:
    """Wildcard subscriber that appends events to Postgres.

    NOTE: writes happen in their own transaction, after the publisher's work
    has committed. A transactional outbox replaces this when execution flows
    arrive (see docs/architecture.md, "Known limitations").
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __call__(self, event: Event) -> None:
        async with self._session_factory() as session:
            session.add(
                EventRecord(
                    id=event.id,
                    event_type=event.type,
                    aggregate_type=event.aggregate_type,
                    aggregate_id=event.aggregate_id,
                    payload=event.model_dump(mode="json")["payload"],
                    correlation_id=event.correlation_id,
                    causation_id=event.causation_id,
                    occurred_at=event.occurred_at,
                )
            )
            await session.commit()

import uuid

from app.events import Event, InMemoryEventBus
from app.events.bus import WILDCARD


async def test_publish_dispatches_to_type_and_wildcard_handlers() -> None:
    bus = InMemoryEventBus()
    seen: list[str] = []

    async def typed(e: Event) -> None:
        seen.append(f"typed:{e.type}")

    async def wildcard(e: Event) -> None:
        seen.append(f"any:{e.type}")

    bus.subscribe("a.happened", typed)
    bus.subscribe(WILDCARD, wildcard)
    await bus.publish(Event(type="a.happened"))
    await bus.publish(Event(type="b.happened"))

    assert sorted(seen) == ["any:a.happened", "any:b.happened", "typed:a.happened"]


async def test_failing_handler_is_isolated() -> None:
    bus = InMemoryEventBus()
    called: list[bool] = []

    async def boom(_: Event) -> None:
        raise RuntimeError("boom")

    async def ok(_: Event) -> None:
        called.append(True)

    bus.subscribe("x", boom)
    bus.subscribe("x", ok)
    await bus.publish(Event(type="x"))  # must not raise
    assert called == [True]


async def test_unsubscribe_and_duplicate_subscribe() -> None:
    bus = InMemoryEventBus()
    count = 0

    async def h(_: Event) -> None:
        nonlocal count
        count += 1

    bus.subscribe("x", h)
    bus.subscribe("x", h)
    await bus.publish(Event(type="x"))
    bus.unsubscribe("x", h)
    await bus.publish(Event(type="x"))
    assert count == 1


def test_caused_event_inherits_correlation() -> None:
    root = Event(type="root")
    child = root.caused("child", aggregate_id=uuid.uuid4())
    grandchild = child.caused("grandchild")
    assert child.correlation_id == root.id
    assert child.causation_id == root.id
    assert grandchild.correlation_id == root.id
    assert grandchild.causation_id == child.id

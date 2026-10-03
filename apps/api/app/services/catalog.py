"""Application services for Phase 0 entities.

Services own business rules and emit domain events; routes stay thin.
"""

from __future__ import annotations

import uuid

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, FeatureDisabledError, NotFoundError
from app.events import Event, EventBus, EventType
from app.models import BrokerAccount, Instrument, Signal, SignalSource
from app.models.enums import ExecutionMode, SignalParser, SignalStatus
from app.schemas.broker_account import BrokerAccountCreate
from app.schemas.instrument import InstrumentCreate
from app.schemas.signal import SignalCreate
from app.schemas.signal_source import SignalSourceCreate, SignalSourceUpdate
from app.services.repository import Repository


class InstrumentService:
    def __init__(self, session: AsyncSession, bus: EventBus) -> None:
        self.repo = Repository(session, Instrument)
        self.bus = bus

    async def create(self, data: InstrumentCreate) -> Instrument:
        obj = await self.repo.add(Instrument(**data.model_dump()))
        await self.bus.publish(
            Event(
                type=EventType.INSTRUMENT_CREATED,
                aggregate_type="instrument",
                aggregate_id=obj.id,
                payload={"exchange": obj.exchange, "tradingsymbol": obj.tradingsymbol},
            )
        )
        return obj


class SignalSourceService:
    def __init__(self, session: AsyncSession, bus: EventBus) -> None:
        self.repo = Repository(session, SignalSource)
        self.bus = bus

    async def create(self, data: SignalSourceCreate) -> SignalSource:
        obj = await self.repo.add(SignalSource(**data.model_dump()))
        await self.bus.publish(
            Event(
                type=EventType.SIGNAL_SOURCE_CREATED,
                aggregate_type="signal_source",
                aggregate_id=obj.id,
                payload={"kind": obj.kind, "name": obj.name},
            )
        )
        return obj

    async def update(self, source_id: uuid.UUID, data: SignalSourceUpdate) -> SignalSource:
        obj = await self.repo.get(source_id)
        changes = data.model_dump(exclude_none=True)
        for k, v in changes.items():
            setattr(obj, k, v)
        await self.repo.session.commit()
        await self.repo.session.refresh(obj)
        await self.bus.publish(
            Event(
                type=EventType.SIGNAL_SOURCE_UPDATED,
                aggregate_type="signal_source",
                aggregate_id=obj.id,
                payload={"changes": sorted(changes)},
            )
        )
        return obj

    async def delete(self, source_id: uuid.UUID) -> None:
        obj = await self.repo.get(source_id)
        session = self.repo.session
        if await session.scalar(select(exists().where(Signal.source_id == source_id))):
            raise ConflictError("Source has signals; disable it instead of deleting.")
        await session.delete(obj)
        await session.commit()
        await self.bus.publish(
            Event(
                type=EventType.SIGNAL_SOURCE_DELETED,
                aggregate_type="signal_source",
                aggregate_id=source_id,
                payload={"name": obj.name},
            )
        )


class BrokerAccountService:
    def __init__(self, session: AsyncSession, bus: EventBus) -> None:
        self.repo = Repository(session, BrokerAccount)
        self.bus = bus

    async def create(self, data: BrokerAccountCreate) -> BrokerAccount:
        if data.mode is ExecutionMode.LIVE:
            raise FeatureDisabledError("Live broker accounts cannot be created in Phase 0.")
        obj = await self.repo.add(BrokerAccount(**data.model_dump()))
        await self.bus.publish(
            Event(
                type=EventType.BROKER_ACCOUNT_CREATED,
                aggregate_type="broker_account",
                aggregate_id=obj.id,
                payload={"broker": obj.broker, "label": obj.label, "mode": obj.mode},
            )
        )
        return obj


class SignalService:
    def __init__(self, session: AsyncSession, bus: EventBus) -> None:
        self.session = session
        self.repo = Repository(session, Signal)
        self.bus = bus

    async def create_manual(self, data: SignalCreate) -> Signal:
        await self._require(SignalSource, data.source_id)
        if data.instrument_id is not None:
            await self._require(Instrument, data.instrument_id)

        values = data.model_dump()
        values["targets"] = [str(t) for t in data.targets]
        obj = await self.repo.add(
            Signal(**values, parser=SignalParser.MANUAL, status=SignalStatus.NEW)
        )
        await self.bus.publish(
            Event(
                type=EventType.SIGNAL_CREATED,
                aggregate_type="signal",
                aggregate_id=obj.id,
                payload={"symbol_text": obj.symbol_text, "side": obj.side, "parser": obj.parser},
            )
        )
        return obj

    async def _require(self, model: type[Instrument] | type[SignalSource], id_: uuid.UUID) -> None:
        if await self.session.get(model, id_) is None:
            raise NotFoundError(f"{model.__name__} {id_} not found")

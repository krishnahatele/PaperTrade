"""Broker connections (Dhan, Kite, ...): credentials, connection test, positions.

Everything here is read-only towards the broker. Orders stay paper."""

from __future__ import annotations

from fastapi import APIRouter, status
from pydantic import BaseModel, Field, ValidationError

from app.adapters.broker.base import BrokerPosition
from app.adapters.broker.providers import BROKERS, BrokerInfo, BrokerProvider
from app.api.deps import ContainerDep
from app.core.errors import InvalidInputError
from app.events import Event, EventType
from app.services.brokers import BrokerStatus, ConnectionTest
from app.services.runtime import BrokerRuntime

router = APIRouter(prefix="/brokers", tags=["brokers"])


class CredentialsBody(BaseModel):
    values: dict[str, str] = Field(description="Field name -> value; blank values are ignored")


class BrokerSettingsBody(BaseModel):
    primary: str | None = None
    market_data: str | None = None
    history: str | None = None


@router.get("/providers", response_model=list[BrokerInfo])
async def providers() -> list[BrokerInfo]:
    return list(BROKERS.values())


@router.get("", response_model=list[BrokerStatus], summary="Every broker and its status")
async def list_brokers(container: ContainerDep) -> list[BrokerStatus]:
    return await container.brokers.status()


@router.get("/settings", response_model=BrokerRuntime)
async def get_broker_settings(container: ContainerDep) -> BrokerRuntime:
    return await container.runtime.get(BrokerRuntime)


@router.patch("/settings", response_model=BrokerRuntime)
async def patch_broker_settings(body: BrokerSettingsBody, container: ContainerDep) -> BrokerRuntime:
    changes = body.model_dump(exclude_none=True)
    try:
        updated = await container.runtime.update(BrokerRuntime, **changes)
    except ValidationError as exc:
        raise InvalidInputError(str(exc.errors()[0]["msg"])) from exc
    if updated.primary is not BrokerProvider.PAPER and not BROKERS[updated.primary].available:
        raise InvalidInputError(f"{BROKERS[updated.primary].label} is not supported yet.")
    await container.market.reload()
    await container.bus.publish(
        Event(
            type=EventType.SETTINGS_UPDATED,
            aggregate_type="settings",
            payload={"section": "broker", "fields": sorted(changes)},
        )
    )
    return updated


@router.put("/{provider}/credentials", response_model=list[BrokerStatus])
async def save_credentials(
    provider: BrokerProvider, body: CredentialsBody, container: ContainerDep
) -> list[BrokerStatus]:
    await container.brokers.save(provider, body.values)
    await container.market.reload()
    return await container.brokers.status()


@router.delete("/{provider}/credentials", status_code=status.HTTP_204_NO_CONTENT)
async def clear_credentials(provider: BrokerProvider, container: ContainerDep) -> None:
    await container.brokers.clear(provider)
    await container.market.reload()


@router.post(
    "/{provider}/test",
    response_model=ConnectionTest,
    summary="Read-only check: profile, funds, positions (never places orders)",
)
async def test_connection(provider: BrokerProvider, container: ContainerDep) -> ConnectionTest:
    return await container.brokers.test(provider)


@router.get("/{provider}/positions", response_model=list[BrokerPosition])
async def broker_positions(
    provider: BrokerProvider, container: ContainerDep
) -> list[BrokerPosition]:
    result = await container.brokers.test(provider)
    if not result.ok:
        raise InvalidInputError(result.error or "Could not read positions.")
    return result.positions


@router.post("/dhan/renew-token", summary="Extend the Dhan access token by 24 hours now")
async def renew_dhan(container: ContainerDep) -> dict[str, bool]:
    ok = await container.brokers.renew_dhan_if_due(force=True)
    if ok:
        await container.market.reload()
    return {"renewed": ok}


@router.post(
    "/dhan/sync-instruments",
    summary="Download Dhan's instrument list and attach Dhan ids to ours",
)
async def sync_dhan(container: ContainerDep) -> dict[str, int]:
    return await container.instruments.sync_dhan_ids()

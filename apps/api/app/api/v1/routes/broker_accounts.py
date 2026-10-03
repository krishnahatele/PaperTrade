from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from pydantic import ValidationError

from app.api.deps import BusDep, PageDep, SessionDep
from app.core.errors import InvalidInputError
from app.events import Event, EventType
from app.models import BrokerAccount
from app.schemas.broker_account import BrokerAccountCreate, BrokerAccountRead, BrokerAccountUpdate
from app.schemas.common import Page
from app.services.catalog import BrokerAccountService
from app.services.repository import Repository
from app.services.risk import AccountRiskSettings

router = APIRouter(prefix="/broker-accounts", tags=["broker-accounts"])


@router.get("", response_model=Page[BrokerAccountRead])
async def list_broker_accounts(session: SessionDep, page: PageDep) -> Page[BrokerAccountRead]:
    rows, total = await Repository(session, BrokerAccount).list(
        order_by=[BrokerAccount.label], limit=page.limit, offset=page.offset
    )
    return Page(
        items=[BrokerAccountRead.model_validate(r) for r in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{account_id}", response_model=BrokerAccountRead)
async def get_broker_account(account_id: uuid.UUID, session: SessionDep) -> BrokerAccount:
    return await Repository(session, BrokerAccount).get(account_id)


@router.post("", response_model=BrokerAccountRead, status_code=status.HTTP_201_CREATED)
async def create_broker_account(
    data: BrokerAccountCreate, session: SessionDep, bus: BusDep
) -> BrokerAccount:
    return await BrokerAccountService(session, bus).create(data)


@router.patch("/{account_id}", response_model=BrokerAccountRead)
async def update_broker_account(
    account_id: uuid.UUID, body: BrokerAccountUpdate, session: SessionDep, bus: BusDep
) -> BrokerAccount:
    acct = await Repository(session, BrokerAccount).get(account_id)
    if body.label is not None:
        acct.label = body.label
    if body.is_active is not None:
        acct.is_active = body.is_active
    if body.settings is not None:
        try:
            merged = AccountRiskSettings.model_validate({**acct.settings, **body.settings})
        except ValidationError as exc:
            err = exc.errors()[0]
            raise InvalidInputError(f"{'.'.join(map(str, err['loc']))}: {err['msg']}") from exc
        acct.settings = merged.model_dump(mode="json")
    await session.commit()
    await session.refresh(acct)
    await bus.publish(
        Event(
            type=EventType.BROKER_ACCOUNT_UPDATED,
            aggregate_type="broker_account",
            aggregate_id=acct.id,
            payload={"fields": sorted(body.model_dump(exclude_none=True))},
        )
    )
    return acct

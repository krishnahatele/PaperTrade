from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import BusDep, PageDep, SessionDep
from app.models import BrokerAccount
from app.schemas.broker_account import BrokerAccountCreate, BrokerAccountRead
from app.schemas.common import Page
from app.services.catalog import BrokerAccountService
from app.services.repository import Repository

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

"""Replay (backtest) of past Telegram signals. Separate from live paper trading."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Query, status
from fastapi.responses import Response
from sqlalchemy import delete, func, select

from app.api.deps import ContainerDep, PageDep, SessionDep
from app.core.errors import InvalidInputError
from app.models import ReplayRun, ReplayTrade
from app.models.enums import ExitReason, ReplayOutcome, ReplayStatus, Side
from app.schemas.common import Page, ReadModel
from app.services.replay import ReplayParams
from app.services.repository import Repository

router = APIRouter(prefix="/replays", tags=["replay"])


class ReplayRunRead(ReadModel):
    name: str
    status: ReplayStatus
    params: dict[str, Any]
    progress: dict[str, Any]
    report: dict[str, Any]
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None


class ReplayRunBrief(ReadModel):
    name: str
    status: ReplayStatus
    progress: dict[str, Any]
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    overall: dict[str, Any] | None = None


class ReplayTradeRead(ReadModel):
    run_id: uuid.UUID
    source_name: str
    message_text: str
    message_at: datetime
    outcome: ReplayOutcome
    tradingsymbol: str | None
    segment: str | None
    side: Side | None
    signal: dict[str, Any]
    quantity: int | None
    entry_price: Decimal | None
    entry_at: datetime | None
    exit_price: Decimal | None
    exit_at: datetime | None
    exit_reason: ExitReason | None
    targets_hit: int
    gross_pnl: Decimal | None
    charges: Decimal | None
    net_pnl: Decimal | None
    r_multiple: Decimal | None
    mfe: Decimal | None
    mae: Decimal | None
    legs: list[dict[str, Any]]
    notes: str | None


@router.post("", response_model=ReplayRunRead, status_code=status.HTTP_201_CREATED)
async def start_replay(body: ReplayParams, container: ContainerDep) -> ReplayRun:
    return await container.replay.start(body)


@router.get("", response_model=list[ReplayRunBrief])
async def list_replays(session: SessionDep) -> list[ReplayRunBrief]:
    runs = await session.scalars(select(ReplayRun).order_by(ReplayRun.created_at.desc()).limit(100))
    out = []
    for r in runs:
        b = ReplayRunBrief.model_validate(r)
        b.overall = (r.report or {}).get("overall")
        out.append(b)
    return out


@router.get("/{run_id}", response_model=ReplayRunRead)
async def get_replay(run_id: uuid.UUID, session: SessionDep) -> ReplayRun:
    return await Repository(session, ReplayRun).get(run_id)


@router.post("/{run_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_replay(run_id: uuid.UUID, session: SessionDep, container: ContainerDep) -> None:
    run = await Repository(session, ReplayRun).get(run_id)
    if run.status not in (ReplayStatus.QUEUED, ReplayStatus.RUNNING):
        raise InvalidInputError(f"Replay is already {run.status}.")
    container.replay.cancel(run_id)


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_replay(run_id: uuid.UUID, session: SessionDep) -> None:
    await Repository(session, ReplayRun).get(run_id)
    await session.execute(delete(ReplayRun).where(ReplayRun.id == run_id))
    await session.commit()


def _filters(
    run_id: uuid.UUID, outcome: ReplayOutcome | None, source: str | None, segment: str | None
) -> list[Any]:
    f: list[Any] = [ReplayTrade.run_id == run_id]
    if outcome is not None:
        f.append(ReplayTrade.outcome == outcome)
    if source:
        f.append(ReplayTrade.source_name == source)
    if segment:
        f.append(ReplayTrade.segment == segment)
    return f


@router.get("/{run_id}/trades", response_model=Page[ReplayTradeRead])
async def replay_trades(
    run_id: uuid.UUID,
    session: SessionDep,
    page: PageDep,
    outcome: ReplayOutcome | None = None,
    source: str | None = None,
    segment: str | None = None,
) -> Page[ReplayTradeRead]:
    f = _filters(run_id, outcome, source, segment)
    total = await session.scalar(select(func.count()).select_from(ReplayTrade).where(*f))
    rows = await session.scalars(
        select(ReplayTrade)
        .where(*f)
        .order_by(ReplayTrade.message_at)
        .limit(page.limit)
        .offset(page.offset)
    )
    return Page(
        items=[ReplayTradeRead.model_validate(r) for r in rows],
        total=int(total or 0),
        limit=page.limit,
        offset=page.offset,
    )


CSV_COLUMNS = [
    "message_at",
    "source_name",
    "tradingsymbol",
    "segment",
    "side",
    "outcome",
    "quantity",
    "entry_price",
    "entry_at",
    "exit_price",
    "exit_at",
    "exit_reason",
    "targets_hit",
    "gross_pnl",
    "charges",
    "net_pnl",
    "r_multiple",
    "notes",
    "message_text",
]


@router.get("/{run_id}/trades.csv", summary="Download all replayed signals as CSV")
async def replay_csv(
    run_id: uuid.UUID,
    session: SessionDep,
    outcome: ReplayOutcome | None = Query(default=None),
) -> Response:
    run = await Repository(session, ReplayRun).get(run_id)
    rows = await session.scalars(
        select(ReplayTrade)
        .where(*_filters(run_id, outcome, None, None))
        .order_by(ReplayTrade.message_at)
    )
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLUMNS)
    for r in rows:
        vals = []
        for c in CSV_COLUMNS:
            v = getattr(r, c)
            vals.append(v.value if hasattr(v, "value") else ("" if v is None else str(v)))
        w.writerow(vals)
    name = "".join(ch if ch.isalnum() else "-" for ch in run.name).strip("-") or "replay"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="replay-{name}.csv"'},
    )

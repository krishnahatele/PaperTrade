"""Market news feed, alerts (keyword headlines and sharp market moves)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, or_, select, update

from app.api.deps import ContainerDep, PageDep, SessionDep
from app.core.errors import InvalidInputError
from app.events import Event, EventType
from app.models import Alert, NewsItem
from app.models.enums import AlertKind
from app.schemas.common import Page, ReadModel
from app.services.news import NewsRuntime, WatchState

router = APIRouter(tags=["news"])


class NewsRead(ReadModel):
    source: str
    title: str
    summary: str | None
    url: str
    published_at: datetime
    matched: list[str]
    direction: str | None


class AlertRead(ReadModel):
    kind: AlertKind
    title: str
    body: str | None
    url: str | None
    payload: dict[str, object]
    read: bool


class NewsStatus(BaseModel):
    last_poll: datetime | None
    feed_errors: dict[str, str]


@router.get("/news", response_model=Page[NewsRead])
async def list_news(
    session: SessionDep,
    page: PageDep,
    q: str | None = Query(default=None, max_length=100),
    matched_only: bool = False,
    source: str | None = None,
) -> Page[NewsRead]:
    filters = []
    if q:
        like = f"%{q}%"
        filters.append(or_(NewsItem.title.ilike(like), NewsItem.summary.ilike(like)))
    if matched_only:
        filters.append(func.jsonb_array_length(NewsItem.matched) > 0)
    if source:
        filters.append(NewsItem.source == source)
    total = await session.scalar(select(func.count()).select_from(NewsItem).where(*filters))
    rows = await session.scalars(
        select(NewsItem)
        .where(*filters)
        .order_by(NewsItem.published_at.desc())
        .limit(page.limit)
        .offset(page.offset)
    )
    return Page(
        items=[NewsRead.model_validate(r) for r in rows],
        total=int(total or 0),
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/news/status", response_model=NewsStatus)
async def news_status(container: ContainerDep) -> NewsStatus:
    return NewsStatus(last_poll=container.news.last_poll, feed_errors=container.news.feed_errors)


@router.post("/news/refresh", summary="Fetch all feeds now")
async def refresh_news(container: ContainerDep) -> dict[str, int]:
    return await container.news.poll()


@router.get("/news/settings", response_model=NewsRuntime)
async def news_settings(container: ContainerDep) -> NewsRuntime:
    return await container.news.settings()


@router.put("/news/settings", response_model=NewsRuntime, summary="Feeds, keywords, watches")
async def put_news_settings(body: dict[str, object], container: ContainerDep) -> NewsRuntime:
    allowed = {k: v for k, v in body.items() if k in NewsRuntime.model_fields}
    try:
        updated = await container.runtime.update(NewsRuntime, **allowed)
    except ValidationError as exc:
        err = exc.errors()[0]
        raise InvalidInputError(f"{'.'.join(map(str, err['loc']))}: {err['msg']}") from exc
    await container.bus.publish(
        Event(
            type=EventType.SETTINGS_UPDATED,
            aggregate_type="settings",
            payload={"section": "news", "fields": sorted(allowed)},
        )
    )
    return updated


@router.get("/market/watch", response_model=list[WatchState], summary="Watched instruments now")
async def market_watch(container: ContainerDep) -> list[WatchState]:
    return await container.news.check_moves()


@router.get("/alerts", response_model=Page[AlertRead])
async def list_alerts(
    session: SessionDep,
    page: PageDep,
    kind: AlertKind | None = None,
    unread_only: bool = False,
) -> Page[AlertRead]:
    filters = []
    if kind is not None:
        filters.append(Alert.kind == kind)
    if unread_only:
        filters.append(Alert.read.is_(False))
    total = await session.scalar(select(func.count()).select_from(Alert).where(*filters))
    rows = await session.scalars(
        select(Alert)
        .where(*filters)
        .order_by(Alert.created_at.desc())
        .limit(page.limit)
        .offset(page.offset)
    )
    return Page(
        items=[AlertRead.model_validate(r) for r in rows],
        total=int(total or 0),
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/alerts/unread-count")
async def unread_count(session: SessionDep) -> dict[str, int]:
    n = await session.scalar(select(func.count()).select_from(Alert).where(Alert.read.is_(False)))
    return {"unread": int(n or 0)}


@router.post("/alerts/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def read_all(session: SessionDep) -> None:
    await session.execute(update(Alert).where(Alert.read.is_(False)).values(read=True))
    await session.commit()

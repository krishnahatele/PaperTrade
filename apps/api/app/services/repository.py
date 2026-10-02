"""Generic async repository for simple list / get / add operations."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class Repository(Generic[ModelT]):
    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    async def get(self, id_: uuid.UUID) -> ModelT:
        obj = await self.session.get(self.model, id_)
        if obj is None:
            raise NotFoundError(f"{self.model.__name__} {id_} not found")
        return obj

    async def exists(self, id_: uuid.UUID) -> bool:
        return await self.session.get(self.model, id_) is not None

    async def list(
        self,
        *,
        filters: Sequence[ColumnElement[bool]] = (),
        order_by: Sequence[Any] = (),
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ModelT], int]:
        base: Select[ModelT] = select(self.model).where(*filters)
        total = await self.session.scalar(select(func.count()).select_from(base.subquery()))
        rows = await self.session.scalars(base.order_by(*order_by).limit(limit).offset(offset))
        return list(rows), int(total or 0)

    async def add(self, obj: ModelT) -> ModelT:
        self.session.add(obj)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(f"{self.model.__name__} violates a uniqueness constraint") from exc
        await self.session.refresh(obj)
        return obj

"""Every StrEnum column's CHECK constraint in the migrated database must allow
every value the code can write. Adding an enum member without a migration
that widens the constraint fails here instead of in production."""

import pytest
from httpx import AsyncClient
from sqlalchemy import Enum as SAEnum
from sqlalchemy import text

from app.db.base import Base
from tests.test_paper_trading import ctr

pytestmark = pytest.mark.db


async def test_enum_check_constraints_allow_all_values(db_client: AsyncClient) -> None:
    container = ctr(db_client)
    async with container.db.session_factory() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid) "
                    "FROM pg_constraint WHERE contype = 'c'"
                )
            )
        ).all()
    defs = {(t, n): d for t, n, d in rows}
    missing = []
    checked = 0
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            if not isinstance(col.type, SAEnum) or col.type.enum_class is None:
                continue
            name = f"ck_{table.name}_{col.type.name}"
            definition = defs.get((table.name, name))
            if definition is None:
                missing.append(f"{name} (no constraint)")
                continue
            checked += 1
            for value in col.type.enums:
                if f"'{value}'" not in definition:
                    missing.append(f"{name} lacks '{value}'")
    assert checked > 20
    assert not missing, missing

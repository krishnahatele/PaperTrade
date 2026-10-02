from __future__ import annotations

from sqlalchemy import LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class SecretRecord(TimestampMixin, Base):
    """An encrypted credential. ``ciphertext`` is Fernet-encrypted; the key lives outside the DB."""

    __tablename__ = "secrets"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)

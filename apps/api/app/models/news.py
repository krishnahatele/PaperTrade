from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.enums import AlertKind


class NewsItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A headline from one of the RSS feeds in Settings → News."""

    __tablename__ = "news_items"
    __table_args__ = (Index("ix_news_items_published_at", "published_at"),)

    source: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(1024), unique=True)
    published_at: Mapped[datetime]
    # Watch keywords found in the headline (empty = no alert)
    matched: Mapped[list[Any]] = mapped_column(default=list, server_default="[]")
    # "up" / "down" when the headline says something surged / plunged
    direction: Mapped[str | None] = mapped_column(String(8))


class Alert(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Something worth a look: a keyword headline or a sharp market move."""

    __tablename__ = "alerts"

    kind: Mapped[AlertKind] = mapped_column(str_enum(AlertKind, "alert_kind"), index=True)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(1024))
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    read: Mapped[bool] = mapped_column(default=False, server_default="false", index=True)

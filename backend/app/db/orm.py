"""SQLAlchemy table definitions.

Database-agnostic by construction — every column type here is chosen to
map cleanly onto both SQLite (dev) and Postgres (later), per AGENTS.md.
See the backend README for the specific portability notes (UUIDs as
strings, tags/links as generic JSON, timezone-aware timestamps, the
status enum, FK cascade behavior).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, CheckConstraint, Date, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.models.note import NOTE_BODY_MAX_LENGTH
from app.models.project import (
    DESCRIPTION_MAX_LENGTH,
    LINKS_MAX_ITEMS,
    NAME_MAX_LENGTH,
    NEXT_ACTION_MAX_LENGTH,
    PITCH_MAX_LENGTH,
    TAGS_MAX_ITEMS,
    Status,
)
from app.models.user import DISPLAY_NAME_MAX_LENGTH


class Base(DeclarativeBase):
    pass


def _new_id() -> str:
    return str(uuid.uuid4())


def _max_length(table: str, column: str, limit: int) -> CheckConstraint:
    """A length cap as a CHECK constraint, backing up the API's own
    validation (app/models/). The columns stay Text: length() counts
    characters in both SQLite and Postgres. Names match migration 0002."""
    return CheckConstraint(
        f"length({column}) <= {limit}", name=f"ck_{table}_{column}_length"
    )


def _max_items(table: str, column: str, limit: int) -> CheckConstraint:
    """A cap on the number of entries in a JSON array column.
    json_array_length() exists in both SQLite and Postgres (for the json
    type these columns use there). Names match migration 0003."""
    return CheckConstraint(
        f"json_array_length({column}) <= {limit}", name=f"ck_{table}_{column}_count"
    )


class UserTable(Base):
    __tablename__ = "users"
    __table_args__ = (_max_length("users", "display_name", DISPLAY_NAME_MAX_LENGTH),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    email: Mapped[str] = mapped_column(Text, unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuthIdentityTable(Base):
    """Split from users so other sign-in methods (Apple/Google) can
    attach later without reshaping the users table, per the spec."""

    __tablename__ = "auth_identities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32))
    provider_subject: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProjectTable(Base):
    __tablename__ = "projects"
    __table_args__ = (
        _max_length("projects", "name", NAME_MAX_LENGTH),
        _max_length("projects", "pitch", PITCH_MAX_LENGTH),
        _max_length("projects", "description", DESCRIPTION_MAX_LENGTH),
        _max_length("projects", "next_action", NEXT_ACTION_MAX_LENGTH),
        _max_items("projects", "tags", TAGS_MAX_ITEMS),
        _max_items("projects", "links", LINKS_MAX_ITEMS),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    pitch: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[Status] = mapped_column(
        SAEnum(Status, values_callable=lambda enum_cls: [e.value for e in enum_cls])
    )
    tags: Mapped[list[str]] = mapped_column(JSON)
    excitement: Mapped[int] = mapped_column()
    effort: Mapped[int] = mapped_column()
    potential: Mapped[int] = mapped_column()
    next_action: Mapped[str] = mapped_column(Text)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    links: Mapped[list[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NoteTable(Base):
    __tablename__ = "notes"
    __table_args__ = (_max_length("notes", "body", NOTE_BODY_MAX_LENGTH),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

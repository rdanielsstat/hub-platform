"""SQL-backed data store (SQLAlchemy).

Routers depend on `get_store` and the `UserRecord`/`ProjectRecord`/
`NoteRecord` DTOs below, never on the ORM tables or a `Session` directly —
this module (plus orm.py and session.py) is the entire swappable seam
between routers and however data actually gets persisted.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone

from fastapi import Depends
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.orm import AuthIdentityTable, NoteTable, ProjectTable, UserTable
from app.db.session import get_db_session
from app.models.project import Status


class DuplicateEmailError(Exception):
    """Raised by create_user when the email is already registered.

    Covers the race a plain get_user_by_email pre-check can't: two
    concurrent registrations for the same email can both pass that
    check, but only one insert can win the table's unique constraint.
    """


def _utc(value: datetime) -> datetime:
    """Postgres returns timezone-aware datetimes for `DateTime(timezone=True)`
    columns; SQLite silently strips tzinfo on read. Everything is written
    as UTC, so reattach UTC only when it's missing rather than assuming
    either dialect's behavior."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


@dataclass
class UserRecord:
    id: str
    email: str
    password_hash: str
    display_name: str | None
    created_at: datetime
    updated_at: datetime


@dataclass
class NoteRecord:
    id: str
    project_id: str
    body: str
    created_at: datetime


@dataclass
class ProjectRecord:
    id: str
    owner_id: str
    name: str
    pitch: str
    description: str
    status: Status
    tags: list[str]
    excitement: int
    effort: int
    potential: int
    next_action: str
    target_date: date | None
    links: list[dict]
    created_at: datetime
    updated_at: datetime


def _user_record(user: UserTable, identity: AuthIdentityTable) -> UserRecord:
    return UserRecord(
        id=user.id,
        email=user.email,
        password_hash=identity.password_hash or "",
        display_name=user.display_name,
        created_at=_utc(user.created_at),
        updated_at=_utc(user.updated_at),
    )


def _project_record(row: ProjectTable) -> ProjectRecord:
    return ProjectRecord(
        id=row.id,
        owner_id=row.owner_id,
        name=row.name,
        pitch=row.pitch,
        description=row.description,
        status=row.status,
        tags=list(row.tags),
        excitement=row.excitement,
        effort=row.effort,
        potential=row.potential,
        next_action=row.next_action,
        target_date=row.target_date,
        links=list(row.links),
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
    )


def _note_record(row: NoteTable) -> NoteRecord:
    return NoteRecord(
        id=row.id,
        project_id=row.project_id,
        body=row.body,
        created_at=_utc(row.created_at),
    )


class Store:
    def __init__(self, db: Session) -> None:
        self._db = db

    # -- users ---------------------------------------------------------

    def has_users(self) -> bool:
        """Used only at startup to decide whether to seed (see
        app/db/seed.py and app/main.py): true once any account exists."""
        return self._db.scalar(select(UserTable.id).limit(1)) is not None

    def create_user(
        self, *, email: str, password_hash: str, display_name: str | None = None
    ) -> UserRecord:
        # Normalized to lowercase before storage, matching the
        # case-insensitive lookup in get_user_by_email — otherwise the
        # unique constraint (case-sensitive) can't stop Foo@x.com and
        # foo@x.com from both being created as separate accounts.
        email = email.lower()
        now = datetime.now(timezone.utc)
        user = UserTable(
            id=str(uuid.uuid4()),
            email=email,
            display_name=display_name,
            created_at=now,
            updated_at=now,
        )
        try:
            self._db.add(user)
            self._db.flush()  # ensure the users row exists before the FK-dependent insert
            identity = AuthIdentityTable(
                id=str(uuid.uuid4()),
                user_id=user.id,
                provider="password",
                provider_subject=email,
                password_hash=password_hash,
                created_at=now,
            )
            self._db.add(identity)
            self._db.commit()
        except IntegrityError as exc:
            self._db.rollback()
            raise DuplicateEmailError(email) from exc
        return _user_record(user, identity)

    def get_user(self, user_id: str) -> UserRecord | None:
        user = self._db.get(UserTable, user_id)
        if user is None:
            return None
        identity = self._get_password_identity(user_id)
        if identity is None:
            return None
        return _user_record(user, identity)

    def get_user_by_email(self, email: str) -> UserRecord | None:
        user = self._db.scalar(
            select(UserTable).where(func.lower(UserTable.email) == email.lower())
        )
        if user is None:
            return None
        identity = self._get_password_identity(user.id)
        if identity is None:
            return None
        return _user_record(user, identity)

    def delete_user_and_owned_data(self, user_id: str) -> None:
        """Delete one user and everything they own, in one transaction:
        notes on their projects, their projects, their auth identities,
        then the user row. Used only by the demo reset (see
        app/bootstrap_db.py). Every statement is filtered by this user's
        id, rather than relying on the FK cascades, so what gets deleted
        is visible here and doesn't depend on SQLite's FK pragma."""
        owned_projects = select(ProjectTable.id).where(ProjectTable.owner_id == user_id)
        try:
            self._db.execute(
                delete(NoteTable).where(NoteTable.project_id.in_(owned_projects))
            )
            self._db.execute(
                delete(ProjectTable).where(ProjectTable.owner_id == user_id)
            )
            self._db.execute(
                delete(AuthIdentityTable).where(AuthIdentityTable.user_id == user_id)
            )
            self._db.execute(delete(UserTable).where(UserTable.id == user_id))
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise

    def _get_password_identity(self, user_id: str) -> AuthIdentityTable | None:
        return self._db.scalar(
            select(AuthIdentityTable).where(
                AuthIdentityTable.user_id == user_id,
                AuthIdentityTable.provider == "password",
            )
        )

    # -- projects --------------------------------------------------------
    # Every lookup takes owner_id alongside the id: a project that exists
    # but belongs to someone else is indistinguishable from one that
    # doesn't exist, by design (see openapi.yaml's NotFound response).

    def list_projects(self, owner_id: str) -> list[ProjectRecord]:
        rows = self._db.scalars(
            select(ProjectTable).where(ProjectTable.owner_id == owner_id)
        )
        return [_project_record(r) for r in rows]

    def get_project(self, project_id: str, owner_id: str) -> ProjectRecord | None:
        row = self._db.get(ProjectTable, project_id)
        if row is None or row.owner_id != owner_id:
            return None
        return _project_record(row)

    def create_project(
        self,
        *,
        owner_id: str,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        **fields: object,
    ) -> ProjectRecord:
        # created_at/updated_at overrides exist only for seeding varied,
        # realistic timestamps (see app/db/seed.py); routers never pass
        # them, so request-driven creates still just stamp "now".
        now = datetime.now(timezone.utc)
        row = ProjectTable(
            id=str(uuid.uuid4()),
            owner_id=owner_id,
            created_at=created_at or now,
            updated_at=updated_at or now,
            **fields,
        )
        self._db.add(row)
        self._db.commit()
        return _project_record(row)

    def update_project(
        self, project_id: str, owner_id: str, **patch: object
    ) -> ProjectRecord | None:
        row = self._db.get(ProjectTable, project_id)
        if row is None or row.owner_id != owner_id:
            return None
        for key, value in patch.items():
            setattr(row, key, value)
        row.updated_at = datetime.now(timezone.utc)
        self._db.commit()
        return _project_record(row)

    def delete_project(self, project_id: str, owner_id: str) -> bool:
        row = self._db.get(ProjectTable, project_id)
        if row is None or row.owner_id != owner_id:
            return False
        self._db.delete(row)
        self._db.commit()
        return True

    # -- notes -----------------------------------------------------------
    # Notes have no owner of their own; ownership is reached via the
    # parent project, so callers check that separately before calling
    # these (see app/routers/notes.py).

    def list_notes(self, project_id: str) -> list[NoteRecord]:
        rows = self._db.scalars(
            select(NoteTable)
            .where(NoteTable.project_id == project_id)
            .order_by(NoteTable.created_at.desc())
        )
        return [_note_record(r) for r in rows]

    def get_note(self, note_id: str) -> NoteRecord | None:
        row = self._db.get(NoteTable, note_id)
        return _note_record(row) if row is not None else None

    def create_note(
        self, *, project_id: str, body: str, created_at: datetime | None = None
    ) -> NoteRecord:
        # created_at override exists only for seeding (see create_project).
        row = NoteTable(
            id=str(uuid.uuid4()),
            project_id=project_id,
            body=body,
            created_at=created_at or datetime.now(timezone.utc),
        )
        self._db.add(row)
        self._db.commit()
        return _note_record(row)

    def delete_note(self, note_id: str) -> None:
        row = self._db.get(NoteTable, note_id)
        if row is not None:
            self._db.delete(row)
            self._db.commit()


def get_store(db: Session = Depends(get_db_session)) -> Store:
    return Store(db)

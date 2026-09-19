"""In-memory data store.

This is the seam that gets swapped for a real database (SQLite via
SQLAlchemy, per AGENTS.md) later. Routers depend on `get_store`, never on
`InMemoryStore` directly, so that swap only touches this module and the
dependency wiring in app/main.py.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone

from app.models.project import Status


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


class InMemoryStore:
    def __init__(self) -> None:
        self._users: dict[str, UserRecord] = {}
        self._users_by_email: dict[str, str] = {}
        self._projects: dict[str, ProjectRecord] = {}
        self._notes: dict[str, NoteRecord] = {}

    # -- users ---------------------------------------------------------

    def create_user(
        self, *, email: str, password_hash: str, display_name: str | None = None
    ) -> UserRecord:
        now = datetime.now(timezone.utc)
        user = UserRecord(
            id=str(uuid.uuid4()),
            email=email,
            password_hash=password_hash,
            display_name=display_name,
            created_at=now,
            updated_at=now,
        )
        self._users[user.id] = user
        self._users_by_email[email.lower()] = user.id
        return user

    def get_user(self, user_id: str) -> UserRecord | None:
        return self._users.get(user_id)

    def get_user_by_email(self, email: str) -> UserRecord | None:
        user_id = self._users_by_email.get(email.lower())
        return self._users.get(user_id) if user_id else None

    # -- projects --------------------------------------------------------
    # Every lookup takes owner_id alongside the id: a project that exists
    # but belongs to someone else is indistinguishable from one that
    # doesn't exist, by design (see openapi.yaml's NotFound response).

    def list_projects(self, owner_id: str) -> list[ProjectRecord]:
        return [p for p in self._projects.values() if p.owner_id == owner_id]

    def get_project(self, project_id: str, owner_id: str) -> ProjectRecord | None:
        record = self._projects.get(project_id)
        if record is None or record.owner_id != owner_id:
            return None
        return record

    def create_project(self, *, owner_id: str, **fields: object) -> ProjectRecord:
        now = datetime.now(timezone.utc)
        record = ProjectRecord(
            id=str(uuid.uuid4()),
            owner_id=owner_id,
            created_at=now,
            updated_at=now,
            **fields,
        )
        self._projects[record.id] = record
        return record

    def update_project(
        self, project_id: str, owner_id: str, **patch: object
    ) -> ProjectRecord | None:
        record = self.get_project(project_id, owner_id)
        if record is None:
            return None
        for key, value in patch.items():
            setattr(record, key, value)
        record.updated_at = datetime.now(timezone.utc)
        return record

    def delete_project(self, project_id: str, owner_id: str) -> bool:
        record = self.get_project(project_id, owner_id)
        if record is None:
            return False
        del self._projects[record.id]
        return True

    # -- notes -----------------------------------------------------------
    # Notes have no owner of their own; ownership is reached via the
    # parent project, so callers check that separately before calling
    # these (see app/routers/notes.py).

    def list_notes(self, project_id: str) -> list[NoteRecord]:
        notes = [n for n in self._notes.values() if n.project_id == project_id]
        notes.sort(key=lambda n: n.created_at, reverse=True)
        return notes

    def get_note(self, note_id: str) -> NoteRecord | None:
        return self._notes.get(note_id)

    def create_note(self, *, project_id: str, body: str) -> NoteRecord:
        note = NoteRecord(
            id=str(uuid.uuid4()),
            project_id=project_id,
            body=body,
            created_at=datetime.now(timezone.utc),
        )
        self._notes[note.id] = note
        return note

    def delete_note(self, note_id: str) -> None:
        self._notes.pop(note_id, None)


store = InMemoryStore()


def get_store() -> InMemoryStore:
    return store

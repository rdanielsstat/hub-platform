"""Usage caps: total accounts, projects per user, notes per project.

Routers call these before creating anything. Over a cap, 403 with a
message the frontend shows as-is (see frontend/src/lib/errors.ts). The
limits come from app/core/config.py (MAX_ACCOUNTS, MAX_PROJECTS_PER_USER,
MAX_NOTES_PER_PROJECT), read at call time so tests can change them; 0
turns a cap off.

Soft caps: count, then insert, with no lock between. Two requests racing
at the boundary can both succeed, leaving a user one or two over. That's
acceptable for what these are for (bounding how much one account, or a
burst of sign-ups, can make the database hold), and keeps every write a
single cheap COUNT plus the insert.
"""

from fastapi import HTTPException, status

from app.core import config
from app.db.store import Store


def _over(limit: int, count: int) -> bool:
    return limit > 0 and count >= limit


def enforce_account_cap(store: Store) -> None:
    if _over(config.MAX_ACCOUNTS, store.count_users()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sign-ups are closed: this instance has reached its account limit.",
        )


def enforce_project_cap(store: Store, owner_id: str) -> None:
    limit = config.MAX_PROJECTS_PER_USER
    if _over(limit, store.count_projects(owner_id)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Project limit reached ({limit}). Delete a project to add another.",
        )


def enforce_note_cap(store: Store, project_id: str) -> None:
    limit = config.MAX_NOTES_PER_PROJECT
    if _over(limit, store.count_notes(project_id)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Note limit reached for this project ({limit}).",
        )

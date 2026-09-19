"""Seed data so the API has something to log in to and look at.

Applied once, to the module-level store singleton, at app startup (see
app/main.py). Not applied to the fresh store instances tests construct.
"""

from app.auth.security import hash_password
from app.db.store import InMemoryStore
from app.models.project import Status

SEED_USER_EMAIL = "demo@hub.dev"
SEED_USER_PASSWORD = "demo1234"


def seed(store: InMemoryStore) -> None:
    user = store.create_user(
        email=SEED_USER_EMAIL,
        password_hash=hash_password(SEED_USER_PASSWORD),
        display_name="Demo User",
    )
    store.create_project(
        owner_id=user.id,
        name="This Incubator",
        pitch="The platform itself: one home to capture, triage, and graduate every idea.",
        description=(
            "A personal platform to capture, organize, and triage project "
            "ideas. Exists to stop the scatter, not to become a thing "
            "endlessly polished instead of shipping."
        ),
        status=Status.ACTIVE,
        tags=["meta", "tools"],
        excitement=5,
        effort=3,
        potential=4,
        next_action="Wire the frontend to the real API.",
        target_date=None,
        links=[{"label": "Repo", "url": "https://github.com"}],
    )
    store.create_project(
        owner_id=user.id,
        name="Chess Improvement Analytics",
        pitch="Turn game history into a targeted improvement plan.",
        description=(
            "Analyze chess game history to surface recurring mistakes and "
            "a focused improvement plan."
        ),
        status=Status.EXPLORING,
        tags=["chess", "stats"],
        excitement=5,
        effort=2,
        potential=3,
        next_action="Export game archive from Lichess/Chess.com API.",
        target_date=None,
        links=[{"label": None, "url": "https://lichess.org/api"}],
    )

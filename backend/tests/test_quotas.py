"""Usage caps (app/core/quotas.py): accounts, projects per user, notes
per project. Limits are lowered per test by patching app.core.config,
which the quota checks read at call time."""

import pytest

from app.core import config
from tests.conftest import TEST_PASSWORD


@pytest.fixture()
def caps(monkeypatch):
    def _set(**limits: int) -> None:
        for name, value in limits.items():
            monkeypatch.setattr(config, name, value)

    return _set


def _register(client, email: str):
    return client.post("/auth/register", json={"email": email, "password": TEST_PASSWORD})


def test_defaults_are_on_for_projects_and_notes():
    assert config.MAX_PROJECTS_PER_USER == 500
    assert config.MAX_NOTES_PER_PROJECT == 500


def test_account_cap_is_off_locally_by_default():
    assert config.MAX_ACCOUNTS == 0


# ---- accounts ----


def test_sign_up_is_refused_once_the_account_cap_is_reached(client, caps):
    caps(MAX_ACCOUNTS=2)

    assert _register(client, "one@example.com").status_code == 201
    assert _register(client, "two@example.com").status_code == 201
    refused = _register(client, "three@example.com")

    assert refused.status_code == 403
    assert "account limit" in refused.json()["detail"]
    # Existing accounts still log in.
    login = client.post(
        "/auth/login", data={"username": "one@example.com", "password": TEST_PASSWORD}
    )
    assert login.status_code == 200


def test_account_cap_counts_accounts_made_outside_sign_up(client, store, caps):
    caps(MAX_ACCOUNTS=1)
    store.create_user(email="seeded@example.com", password_hash="x")

    assert _register(client, "new@example.com").status_code == 403


def test_duplicate_email_is_still_409_at_the_account_cap(client, caps):
    caps(MAX_ACCOUNTS=1)
    _register(client, "dup@example.com")

    assert _register(client, "dup@example.com").status_code == 409


def test_account_cap_of_zero_is_off(client, caps):
    caps(MAX_ACCOUNTS=0)

    for i in range(5):
        assert _register(client, f"u{i}@example.com").status_code == 201


# ---- projects ----


def test_project_create_is_refused_at_the_per_user_cap(client, register_and_login, caps):
    caps(MAX_PROJECTS_PER_USER=2)
    alice = register_and_login("alice@example.com")
    bob = register_and_login("bob@example.com")

    for name in ("a", "b"):
        assert client.post("/projects", json={"name": name}, headers=alice).status_code == 201
    refused = client.post("/projects", json={"name": "c"}, headers=alice)

    assert refused.status_code == 403
    assert refused.json()["detail"] == (
        "Project limit reached (2). Delete a project to add another."
    )
    # Per user: someone else is unaffected.
    assert client.post("/projects", json={"name": "b1"}, headers=bob).status_code == 201


def test_deleting_a_project_frees_a_slot(client, register_and_login, caps):
    caps(MAX_PROJECTS_PER_USER=1)
    headers = register_and_login("carol@example.com")
    first = client.post("/projects", json={"name": "a"}, headers=headers).json()
    assert client.post("/projects", json={"name": "b"}, headers=headers).status_code == 403

    client.delete(f"/projects/{first['id']}", headers=headers)

    assert client.post("/projects", json={"name": "b"}, headers=headers).status_code == 201


def test_updates_are_allowed_at_the_project_cap(client, register_and_login, caps):
    caps(MAX_PROJECTS_PER_USER=1)
    headers = register_and_login("dave@example.com")
    project = client.post("/projects", json={"name": "a"}, headers=headers).json()

    res = client.patch(f"/projects/{project['id']}", json={"name": "renamed"}, headers=headers)

    assert res.status_code == 200


# ---- notes ----


def test_note_create_is_refused_at_the_per_project_cap(client, register_and_login, caps):
    caps(MAX_NOTES_PER_PROJECT=2)
    headers = register_and_login("erin@example.com")
    full = client.post("/projects", json={"name": "full"}, headers=headers).json()
    other = client.post("/projects", json={"name": "other"}, headers=headers).json()

    for body in ("one", "two"):
        res = client.post(f"/projects/{full['id']}/notes", json={"body": body}, headers=headers)
        assert res.status_code == 201
    refused = client.post(f"/projects/{full['id']}/notes", json={"body": "three"}, headers=headers)

    assert refused.status_code == 403
    assert refused.json()["detail"] == "Note limit reached for this project (2)."
    # Per project: another project has its own allowance.
    res = client.post(f"/projects/{other['id']}/notes", json={"body": "x"}, headers=headers)
    assert res.status_code == 201


def test_note_cap_does_not_reveal_other_users_projects(client, register_and_login, caps):
    """Ownership is checked first, so a full project that isn't yours is
    still a 404, not a 403."""
    caps(MAX_NOTES_PER_PROJECT=0)
    owner = register_and_login("owner@example.com")
    intruder = register_and_login("intruder@example.com")
    project = client.post("/projects", json={"name": "p"}, headers=owner).json()
    caps(MAX_NOTES_PER_PROJECT=1)
    client.post(f"/projects/{project['id']}/notes", json={"body": "n"}, headers=owner)

    res = client.post(f"/projects/{project['id']}/notes", json={"body": "x"}, headers=intruder)

    assert res.status_code == 404


# ---- store counts ----


def test_store_counts(store):
    user = store.create_user(email="count@example.com", password_hash="x")
    other = store.create_user(email="other@example.com", password_hash="x")
    project = store.create_project(
        owner_id=user.id, name="p", pitch="", description="", status="Inbox",
        tags=[], excitement=3, effort=3, potential=3, next_action="",
        target_date=None, links=[],
    )
    store.create_note(project_id=project.id, body="n1")
    store.create_note(project_id=project.id, body="n2")

    assert store.count_users() == 2
    assert store.count_projects(user.id) == 1
    assert store.count_projects(other.id) == 0
    assert store.count_notes(project.id) == 2

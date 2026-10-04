"""Auth against real Postgres: sign-up, login, the session cookie, and
the email uniqueness rules that depend on the database."""

from datetime import UTC

import pytest

from app.core import config
from app.core.config import AUTH_COOKIE_NAME
from app.db.store import DuplicateEmailError
from tests.conftest import TEST_PASSWORD

pytestmark = pytest.mark.integration


def _register(client, email: str, password: str = TEST_PASSWORD):
    return client.post("/auth/register", json={"email": email, "password": password})


def test_register_login_and_me(client):
    assert _register(client, "it-user@example.com").status_code == 201
    client.cookies.clear()

    login = client.post(
        "/auth/login",
        data={"username": "it-user@example.com", "password": TEST_PASSWORD},
    )
    assert login.status_code == 200
    assert AUTH_COOKIE_NAME in login.cookies

    # The cookie alone authenticates (the web app's path).
    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "it-user@example.com"

    # So does the bearer token alone (API clients).
    client.cookies.clear()
    token = login.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200


def test_wrong_password_and_unknown_email_are_both_401(client):
    _register(client, "known@example.com")

    wrong = client.post(
        "/auth/login", data={"username": "known@example.com", "password": "nope-nope"}
    )
    unknown = client.post(
        "/auth/login", data={"username": "nobody@example.com", "password": "nope-nope"}
    )

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_email_is_case_insensitive_on_postgres(client):
    """func.lower() lookups and lowercased storage, on a database whose
    text comparison is case-sensitive."""
    assert _register(client, "Mixed.Case@Example.com").status_code == 201
    assert _register(client, "mixed.case@example.com").status_code == 409

    login = client.post(
        "/auth/login",
        data={"username": "MIXED.CASE@EXAMPLE.COM", "password": TEST_PASSWORD},
    )
    assert login.status_code == 200


def test_unique_index_catches_a_duplicate_the_precheck_missed(store):
    """Two concurrent sign-ups can both pass the lookup; Postgres's
    unique index on users.email must stop the second insert."""
    store.create_user(email="race@example.com", password_hash="h1")

    with pytest.raises(DuplicateEmailError):
        store.create_user(email="race@example.com", password_hash="h2")

    # The session is still usable after the rollback.
    assert store.get_user_by_email("race@example.com") is not None


def test_timestamps_come_back_timezone_aware(client):
    _register(client, "tz@example.com")

    me = client.get("/auth/me").json()

    assert me["createdAt"].endswith(("Z", "+00:00"))


def test_store_preserves_utc(store):
    user = store.create_user(email="utc@example.com", password_hash="h")
    again = store.get_user(user.id)

    assert again.created_at.tzinfo is not None
    assert again.created_at.utcoffset() == UTC.utcoffset(None)


def test_account_cap_counts_postgres_rows(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_ACCOUNTS", 2)

    assert _register(client, "cap1@example.com").status_code == 201
    assert _register(client, "cap2@example.com").status_code == 201
    assert _register(client, "cap3@example.com").status_code == 403


def test_over_long_login_password_is_422(client):
    res = client.post(
        "/auth/login", data={"username": "x@example.com", "password": "a" * 257}
    )

    assert res.status_code == 422


def test_display_name_limit_on_postgres(client, store):
    ok = client.post(
        "/auth/register",
        json={
            "email": "dn@example.com",
            "password": TEST_PASSWORD,
            "displayName": "d" * 100,
        },
    )
    too_long = client.post(
        "/auth/register",
        json={
            "email": "dn2@example.com",
            "password": TEST_PASSWORD,
            "displayName": "d" * 101,
        },
    )

    assert ok.status_code == 201
    assert too_long.status_code == 422


def test_check_violation_is_not_reported_as_a_duplicate_email(store):
    """create_user maps only a real email clash to DuplicateEmailError."""
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        store.create_user(
            email="dn3@example.com", password_hash="h", display_name="d" * 101
        )

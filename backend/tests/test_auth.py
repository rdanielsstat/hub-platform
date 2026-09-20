import pytest

from app.db.store import DuplicateEmailError


def test_register_returns_token(client):
    res = client.post(
        "/auth/register", json={"email": "new@example.com", "password": "password123"}
    )
    assert res.status_code == 201
    body = res.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_register_duplicate_email_is_rejected(client):
    client.post(
        "/auth/register", json={"email": "dup@example.com", "password": "password123"}
    )
    res = client.post(
        "/auth/register", json={"email": "dup@example.com", "password": "password123"}
    )
    assert res.status_code == 409


def test_create_user_duplicate_email_raises_not_crashes(store):
    """Covers the race get_user_by_email's pre-check can't: two
    concurrent registrations both pass the check, so the second
    create_user call is the one that has to reject the duplicate."""
    store.create_user(email="race@example.com", password_hash="hash1")

    with pytest.raises(DuplicateEmailError):
        store.create_user(email="race@example.com", password_hash="hash2")

    # the session must still be usable after the rollback
    assert store.get_user_by_email("race@example.com") is not None


def test_login_succeeds_with_correct_password(client):
    client.post(
        "/auth/register",
        json={"email": "login@example.com", "password": "password123"},
    )
    res = client.post(
        "/auth/login",
        data={"username": "login@example.com", "password": "password123"},
    )
    assert res.status_code == 200
    assert res.json()["access_token"]


def test_login_with_wrong_password_is_rejected(client):
    client.post(
        "/auth/register",
        json={"email": "wrongpw@example.com", "password": "password123"},
    )
    res = client.post(
        "/auth/login",
        data={"username": "wrongpw@example.com", "password": "not-the-password"},
    )
    assert res.status_code == 401


def test_protected_endpoint_without_token_is_rejected(client):
    res = client.get("/auth/me")
    assert res.status_code == 401


def test_protected_endpoint_with_invalid_token_is_rejected(client):
    res = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert res.status_code == 401


def test_me_returns_the_logged_in_user(client, register_and_login):
    headers = register_and_login("me@example.com")
    res = client.get("/auth/me", headers=headers)
    assert res.status_code == 200
    assert res.json()["email"] == "me@example.com"

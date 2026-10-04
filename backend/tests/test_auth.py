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


def test_register_password_over_max_length_is_rejected(client):
    res = client.post(
        "/auth/register",
        json={"email": "longpw@example.com", "password": "a" * 257},
    )
    assert res.status_code == 422


def test_login_password_over_max_length_is_rejected_without_hashing(
    client, monkeypatch
):
    def no_hashing(*args: object) -> bool:
        raise AssertionError("an over-long password must not reach argon2")

    monkeypatch.setattr("app.routers.auth.verify_password", no_hashing)

    res = client.post(
        "/auth/login", data={"username": "longpw@example.com", "password": "a" * 257}
    )

    assert res.status_code == 422
    (error,) = res.json()["detail"]
    assert error["loc"] == ["body", "password"]
    assert error["type"] == "string_too_long"
    assert "a" * 257 not in res.text


def test_login_password_at_max_length_is_checked_normally(client):
    password = "b" * 256
    client.post(
        "/auth/register", json={"email": "maxpw@example.com", "password": password}
    )

    ok = client.post(
        "/auth/login", data={"username": "maxpw@example.com", "password": password}
    )
    wrong = client.post(
        "/auth/login", data={"username": "maxpw@example.com", "password": "c" * 256}
    )

    assert ok.status_code == 200
    assert wrong.status_code == 401


def test_over_long_login_attempts_still_count_toward_the_rate_limit(
    client, monkeypatch
):
    from app.auth import rate_limit

    monkeypatch.setattr(
        rate_limit, "login_rate_limiter", rate_limit.SlidingWindowRateLimiter(2)
    )
    form = {"username": "x@example.com", "password": "a" * 1000}

    statuses = [client.post("/auth/login", data=form).status_code for _ in range(3)]

    assert statuses == [422, 422, 429]


def test_register_with_casing_variant_of_existing_email_is_rejected(client):
    client.post(
        "/auth/register", json={"email": "Case@Example.com", "password": "password123"}
    )
    res = client.post(
        "/auth/register", json={"email": "case@example.com", "password": "password123"}
    )
    assert res.status_code == 409


def test_login_works_regardless_of_registered_or_submitted_casing(client):
    client.post(
        "/auth/register",
        json={"email": "MixedCase@Example.com", "password": "password123"},
    )
    res = client.post(
        "/auth/login",
        data={"username": "mixedcase@example.com", "password": "password123"},
    )
    assert res.status_code == 200


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


def test_login_response_does_not_distinguish_unknown_email_from_wrong_password(
    client,
):
    """An unknown email and a wrong password for a real account must be
    indistinguishable to the client, status and body alike, so neither
    the response shape nor (per DUMMY_PASSWORD_HASH) its timing leaks
    which emails are registered."""
    client.post(
        "/auth/register",
        json={"email": "real@example.com", "password": "password123"},
    )

    unknown_res = client.post(
        "/auth/login",
        data={"username": "nobody@example.com", "password": "whatever123"},
    )
    wrong_res = client.post(
        "/auth/login",
        data={"username": "real@example.com", "password": "not-the-password"},
    )

    assert unknown_res.status_code == wrong_res.status_code == 401
    assert unknown_res.json() == wrong_res.json()


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

"""The web app's session: login/register set the JWT in an httpOnly,
SameSite=Strict cookie, protected routes accept it, logout clears it."""

from app.core.config import AUTH_COOKIE_NAME
from tests.conftest import TEST_PASSWORD


def _register(client, email: str):
    return client.post(
        "/auth/register", json={"email": email, "password": TEST_PASSWORD}
    )


def _login(client, email: str):
    return client.post(
        "/auth/login", data={"username": email, "password": TEST_PASSWORD}
    )


def _set_cookie(res) -> str:
    return res.headers["set-cookie"].lower()


def test_login_sets_an_httponly_samesite_strict_session_cookie(client):
    _register(client, "cookie-login@example.com")
    client.cookies.clear()

    res = _login(client, "cookie-login@example.com")

    assert res.status_code == 200
    cookie = _set_cookie(res)
    assert cookie.startswith(f"{AUTH_COOKIE_NAME}=")
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/" in cookie
    # The body still carries the same token, for bearer-header API clients.
    assert client.cookies.get(AUTH_COOKIE_NAME) == res.json()["access_token"]


def test_register_sets_the_session_cookie(client):
    res = _register(client, "cookie-register@example.com")

    assert res.status_code == 201
    assert client.cookies.get(AUTH_COOKIE_NAME) == res.json()["access_token"]


def test_cookie_alone_authenticates(client):
    _register(client, "cookie-only@example.com")

    res = client.get("/auth/me")

    assert res.status_code == 200
    assert res.json()["email"] == "cookie-only@example.com"


def test_bearer_header_wins_over_the_cookie(client):
    other = _register(client, "cookie-other@example.com").json()["access_token"]
    _register(client, "cookie-owner@example.com")  # cookie now belongs to owner

    res = client.get("/auth/me", headers={"Authorization": f"Bearer {other}"})

    assert res.json()["email"] == "cookie-other@example.com"


def test_logout_clears_the_cookie_and_needs_no_credentials(client):
    _register(client, "cookie-logout@example.com")

    res = client.post("/auth/logout")

    assert res.status_code == 204
    cookie = _set_cookie(res)
    assert cookie.startswith(f'{AUTH_COOKIE_NAME}=""') or cookie.startswith(
        f"{AUTH_COOKIE_NAME}=;"
    )
    assert "max-age=0" in cookie
    assert client.cookies.get(AUTH_COOKIE_NAME) is None
    assert client.get("/auth/me").status_code == 401


def test_an_invalid_cookie_is_rejected_and_cleared(client):
    client.cookies.set(AUTH_COOKIE_NAME, "not-a-real-token")

    res = client.get("/auth/me")

    assert res.status_code == 401
    assert "max-age=0" in _set_cookie(res)


def test_an_invalid_bearer_token_does_not_touch_the_cookie(client):
    res = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})

    assert res.status_code == 401
    assert "set-cookie" not in res.headers


def test_no_credentials_at_all_is_a_plain_401(client):
    res = client.get("/auth/me")

    assert res.status_code == 401
    assert res.json() == {"detail": "Not authenticated"}
    assert "set-cookie" not in res.headers

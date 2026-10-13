"""Login CSRF (security/REMEDIATION_LOG.md M4): /auth/login and
/auth/register refuse a request whose Origin header is present and not on
the CORS_ORIGINS allowlist, so another site can't sign a visitor's browser
into an attacker's account. Requests without an Origin (API clients such
as the MCP server, curl, Playwright's request fixture) are unaffected."""

import pytest
from fastapi.testclient import TestClient

from app.core import config
from app.core.config import AUTH_COOKIE_NAME
from tests.conftest import TEST_PASSWORD

ALLOWED = "http://localhost:5173"


def _register(client: TestClient, email: str, origin: str | None):
    headers = {"Origin": origin} if origin is not None else {}
    return client.post(
        "/auth/register",
        json={"email": email, "password": TEST_PASSWORD},
        headers=headers,
    )


def _login(client: TestClient, email: str, origin: str | None):
    headers = {"Origin": origin} if origin is not None else {}
    return client.post(
        "/auth/login",
        data={"username": email, "password": TEST_PASSWORD},
        headers=headers,
    )


def test_an_allowed_origin_works(client):
    assert _register(client, "a@example.com", ALLOWED).status_code == 201
    client.cookies.clear()
    assert _login(client, "a@example.com", ALLOWED).status_code == 200


def test_no_origin_works(client):
    assert _register(client, "b@example.com", None).status_code == 201
    client.cookies.clear()
    assert _login(client, "b@example.com", None).status_code == 200


@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.example",
        "null",
        "http://localhost:5174",
        "https://localhost:5173",
        "http://localhost:5173.evil.example",
    ],
)
def test_a_foreign_origin_is_refused_on_login(client, origin):
    _register(client, "c@example.com", None)
    client.cookies.clear()
    res = _login(client, "c@example.com", origin)
    assert res.status_code == 403
    assert res.json()["detail"] == "Cross-site sign-in refused"
    assert AUTH_COOKIE_NAME not in res.cookies


@pytest.mark.parametrize("origin", ["https://evil.example", "null"])
def test_a_foreign_origin_is_refused_on_register(client, store, origin):
    res = _register(client, "d@example.com", origin)
    assert res.status_code == 403
    assert AUTH_COOKIE_NAME not in res.cookies
    assert store.get_user_by_email("d@example.com") is None


def test_the_deployed_site_origin_is_allowed(client, monkeypatch):
    # Deployed, CORS_ORIGINS is the site itself (infra/hub/lambda.tf).
    monkeypatch.setattr(config, "CORS_ORIGINS", ["https://hub.dnls.dev"])
    assert _register(client, "e@example.com", "https://hub.dnls.dev").status_code == 201
    client.cookies.clear()
    assert _login(client, "e@example.com", "https://hub.dnls.dev").status_code == 200
    assert _login(client, "e@example.com", ALLOWED).status_code == 403


def test_other_routes_are_unaffected(client, register_and_login):
    headers = register_and_login("f@example.com")
    res = client.get("/projects", headers={**headers, "Origin": "https://evil.example"})
    assert res.status_code == 200

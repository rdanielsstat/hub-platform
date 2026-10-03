"""POST /client-errors (app/routers/errors.py): frontend error reports,
logged as one JSON line each."""

import json
import logging

import pytest

from app.auth import rate_limit
from app.auth.rate_limit import SlidingWindowRateLimiter
from app.auth.security import create_access_token
from app.core.config import AUTH_COOKIE_NAME

REPORT = {
    "kind": "error",
    "message": "TypeError: x is undefined",
    "stack": "at foo (app.js:1:2)",
    "url": "https://hub.dnls.dev/project/abc?token=secret#frag",
    "userAgent": "Mozilla/5.0",
}


def _logged(caplog) -> list[dict]:
    return [
        json.loads(r.getMessage().removeprefix("client_error "))
        for r in caplog.records
        if r.name == "app.client_errors"
    ]


def test_report_is_logged_as_json_and_returns_204(client, caplog):
    caplog.set_level(logging.WARNING, logger="app.client_errors")

    res = client.post("/client-errors", json=REPORT)

    assert res.status_code == 204
    (entry,) = _logged(caplog)
    assert entry["kind"] == "error"
    assert entry["message"] == "TypeError: x is undefined"
    assert entry["stack"] == "at foo (app.js:1:2)"
    assert entry["user_agent"] == "Mozilla/5.0"
    assert entry["user_id"] is None


def test_query_string_and_fragment_are_stripped(client, caplog):
    caplog.set_level(logging.WARNING, logger="app.client_errors")

    client.post(
        "/client-errors",
        json={
            **REPORT,
            "kind": "http",
            "endpoint": "https://hub.dnls.dev/api/projects?x=1",
            "method": "GET",
            "status": 503,
        },
    )

    (entry,) = _logged(caplog)
    assert entry["url"] == "https://hub.dnls.dev/project/abc"
    assert entry["endpoint"] == "https://hub.dnls.dev/api/projects"
    assert entry["status"] == 503
    assert "secret" not in json.dumps(entry)


def test_needs_no_session(client):
    client.cookies.clear()

    assert client.post("/client-errors", json=REPORT).status_code == 204


def test_valid_session_cookie_attaches_the_user_id(client, caplog):
    caplog.set_level(logging.WARNING, logger="app.client_errors")
    client.cookies.set(AUTH_COOKIE_NAME, create_access_token("user-123"))

    client.post("/client-errors", json=REPORT)

    assert _logged(caplog)[0]["user_id"] == "user-123"


def test_bearer_token_attaches_the_user_id(client, caplog):
    caplog.set_level(logging.WARNING, logger="app.client_errors")

    client.post(
        "/client-errors",
        json=REPORT,
        headers={"Authorization": f"Bearer {create_access_token('user-456')}"},
    )

    assert _logged(caplog)[0]["user_id"] == "user-456"


def test_invalid_token_is_ignored_not_rejected(client, caplog):
    caplog.set_level(logging.WARNING, logger="app.client_errors")
    client.cookies.set(AUTH_COOKIE_NAME, "garbage")

    res = client.post("/client-errors", json=REPORT)

    assert res.status_code == 204
    assert _logged(caplog)[0]["user_id"] is None


@pytest.mark.parametrize(
    "patch",
    [
        {"kind": "something-else"},
        {"message": "m" * 2001},
        {"stack": "s" * 8001},
        {"url": "u" * 2001},
        {"status": 600},
        {"message": None},
    ],
)
def test_invalid_reports_are_422_and_not_logged(client, caplog, patch):
    caplog.set_level(logging.WARNING, logger="app.client_errors")

    res = client.post("/client-errors", json={**REPORT, **patch})

    assert res.status_code == 422
    assert _logged(caplog) == []


def test_reports_are_rate_limited_per_client(client, monkeypatch):
    monkeypatch.setattr(
        rate_limit, "client_error_rate_limiter", SlidingWindowRateLimiter(2)
    )

    statuses = [client.post("/client-errors", json=REPORT).status_code for _ in range(3)]

    assert statuses == [204, 204, 429]


def test_client_error_limit_is_separate_from_login(client, monkeypatch):
    monkeypatch.setattr(
        rate_limit, "client_error_rate_limiter", SlidingWindowRateLimiter(1)
    )
    monkeypatch.setattr(rate_limit, "login_rate_limiter", SlidingWindowRateLimiter(1))

    assert client.post("/client-errors", json=REPORT).status_code == 204
    login = client.post("/auth/login", data={"username": "a@b.co", "password": "wrong-pass"})
    assert login.status_code == 401

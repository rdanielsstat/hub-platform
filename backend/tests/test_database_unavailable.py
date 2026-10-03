"""A database that can't be reached (Neon resuming, Postgres down) is a
503 with Retry-After, keeps its CORS headers, and never a 401: the web
app must not take it for a signed-out session."""

import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.auth.security import create_access_token
from app.db.store import get_store
from app.main import app


def _unreachable_store():
    raise OperationalError(
        "SELECT 1", {}, ConnectionRefusedError("connection to db.internal refused")
    )


@pytest.fixture()
def client_without_db():
    app.dependency_overrides[get_store] = _unreachable_store
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_session_check_is_503_not_401(client_without_db):
    token = create_access_token("user-1")

    res = client_without_db.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 503
    assert res.headers["Retry-After"] == "2"
    assert res.json() == {
        "detail": "The database is temporarily unavailable. Try again in a moment."
    }


def test_response_does_not_leak_the_database_error(client_without_db):
    token = create_access_token("user-1")

    res = client_without_db.get("/projects", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 503
    assert "db.internal" not in res.text


def test_503_keeps_cors_headers_for_the_dev_frontend(client_without_db):
    res = client_without_db.get(
        "/projects",
        headers={
            "Authorization": f"Bearer {create_access_token('user-1')}",
            "Origin": "http://localhost:5173",
        },
    )

    assert res.status_code == 503
    assert res.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_outage_is_logged_without_the_message(client_without_db, caplog):
    caplog.set_level(logging.WARNING, logger="app.db")

    client_without_db.get(
        "/projects", headers={"Authorization": f"Bearer {create_access_token('u')}"}
    )

    (record,) = [r for r in caplog.records if r.name == "app.db"]
    assert "database_unavailable method=GET path=/projects" in record.getMessage()
    assert "ConnectionRefusedError" in record.getMessage()
    assert "db.internal" not in record.getMessage()


def test_health_does_not_need_the_database(client_without_db):
    assert client_without_db.get("/health").status_code == 200

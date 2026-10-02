import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.origin_verify import OriginVerifyMiddleware

SECRET = "cloudfront-shared-secret"


def _client(secret: str | None) -> TestClient:
    app = FastAPI()

    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"ok": "yes"}

    @app.post("/auth/login")
    def login() -> dict[str, str]:
        return {"reached": "login"}

    app.add_middleware(OriginVerifyMiddleware, secret=secret)
    return TestClient(app)


def test_a_request_through_cloudfront_with_the_secret_gets_through():
    res = _client(SECRET).get("/ping", headers={"X-Origin-Verify": SECRET})

    assert res.status_code == 200
    assert res.json() == {"ok": "yes"}


def test_header_name_is_case_insensitive():
    res = _client(SECRET).get("/ping", headers={"x-origin-verify": SECRET})

    assert res.status_code == 200


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-Origin-Verify": ""},
        {"X-Origin-Verify": "wrong"},
        {"X-Origin-Verify": SECRET + "x"},
        {"X-Origin-Verify": SECRET[:-1]},
    ],
    ids=["missing", "empty", "wrong", "longer", "shorter"],
)
def test_a_direct_call_without_the_right_secret_is_forbidden(headers):
    res = _client(SECRET).get("/ping", headers=headers)

    assert res.status_code == 403
    assert res.json() == {"detail": "Forbidden"}


def test_rejection_happens_before_the_route_runs():
    """A spoofed direct call to /auth/login never reaches the handler (or
    the login rate limit, which a spoofed client IP header would dodge)."""
    res = _client(SECRET).post(
        "/auth/login", headers={"CloudFront-Viewer-Address": "203.0.113.9:443"}
    )

    assert res.status_code == 403
    assert "reached" not in res.text


def test_rejections_are_logged_without_the_secret(caplog):
    client = _client(SECRET)
    with caplog.at_level(logging.WARNING, logger="app.security"):
        client.get("/ping")
        client.get("/ping", headers={"X-Origin-Verify": "wrong-guess"})

    messages = [r.getMessage() for r in caplog.records if r.name == "app.security"]
    assert len(messages) == 2
    assert "reason=missing" in messages[0] and "path=/ping" in messages[0]
    assert "reason=mismatch" in messages[1]
    assert all(SECRET not in m and "wrong-guess" not in m for m in messages)


def test_no_secret_means_the_check_is_off():
    """Local runs (USE_SSM off) pass None: everything gets through."""
    client = _client(None)

    assert client.get("/ping").status_code == 200
    res = client.get("/ping", headers={"X-Origin-Verify": "anything"})
    assert res.status_code == 200

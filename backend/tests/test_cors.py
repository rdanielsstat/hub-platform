from fastapi.testclient import TestClient

from app.core import config
from app.main import app

DEFAULT_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


# ---- parse_cors_origins() ----


def test_cors_origins_default_when_unset():
    assert config.parse_cors_origins(None) == DEFAULT_ORIGINS


def test_cors_origins_default_when_empty():
    assert config.parse_cors_origins("") == DEFAULT_ORIGINS
    assert config.parse_cors_origins("  ,  ") == DEFAULT_ORIGINS


def test_cors_origins_single_origin():
    assert config.parse_cors_origins("https://hub.example") == ["https://hub.example"]


def test_cors_origins_multiple_origins():
    assert config.parse_cors_origins("https://a.example,https://b.example") == [
        "https://a.example",
        "https://b.example",
    ]


def test_cors_origins_tolerates_whitespace_around_entries():
    assert config.parse_cors_origins("  https://a.example ,\thttps://b.example  ,") == [
        "https://a.example",
        "https://b.example",
    ]


# ---- the app as imported (CORS_ORIGINS unset in tests) ----


def _preflight(origin: str):
    return TestClient(app).options(
        "/health",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )


def test_default_origin_gets_allow_header():
    res = _preflight("http://localhost:5173")

    assert res.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_disallowed_origin_gets_no_allow_header():
    res = _preflight("https://evil.example")

    assert "access-control-allow-origin" not in res.headers

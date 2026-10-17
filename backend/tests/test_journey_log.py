"""The project creation journey (app/journey_log.py): one structured log
line per POST /projects, carrying the same trace_id as the request's
span and the latency metric's exemplar, and nothing from the request."""

import json
import logging
import re
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from app.db.store import Store, get_store
from app.journey_log import JourneyLogMiddleware, outcome
from app.routers import auth, projects
from observability import EXPORTED_INFO_LOGGERS, initialize_observability
from tests.conftest import TEST_PASSWORD

EMAIL = "journey.person@example.com"
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_SDK_DISABLED", "ENVIRONMENT"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture()
def telemetry(
    store: Store,
) -> Iterator[
    tuple[
        TestClient,
        InMemorySpanExporter,
        InMemoryMetricReader,
        InMemoryLogRecordExporter,
    ]
]:
    app = FastAPI()
    app.include_router(auth.router)
    app.include_router(projects.router)
    app.add_middleware(JourneyLogMiddleware)
    app.dependency_overrides[get_store] = lambda: store
    spans, metrics, logs = (
        InMemorySpanExporter(),
        InMemoryMetricReader(),
        InMemoryLogRecordExporter(),
    )
    handle = initialize_observability(
        app, span_exporter=spans, metric_reader=metrics, log_exporter=logs
    )
    assert handle is not None
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, spans, metrics, logs
    finally:
        handle.shutdown()


def _headers(client: TestClient) -> dict[str, str]:
    client.post("/auth/register", json={"email": EMAIL, "password": TEST_PASSWORD})
    res = client.post(
        "/auth/login", data={"username": EMAIL, "password": TEST_PASSWORD}
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _journey_lines(logs: InMemoryLogRecordExporter) -> list:
    return [
        r
        for r in logs.get_finished_logs()
        if "project_create" in str(r.log_record.body)
    ]


def _entry(record) -> dict:
    body = str(record.log_record.body)
    return json.loads(body.split(" ", 1)[1])


def test_journey_logger_is_exported_at_info() -> None:
    assert EXPORTED_INFO_LOGGERS == ("app.projects",)


def test_one_line_per_creation_with_matching_trace_id(telemetry) -> None:
    client, spans, metrics, logs = telemetry
    headers = _headers(client)
    spans.clear()

    res = client.post(
        "/projects", json={"name": "Secret plan", "pitch": EMAIL}, headers=headers
    )
    assert res.status_code == 201, res.text

    (record,) = _journey_lines(logs)
    entry = _entry(record)
    assert entry["event"] == "project_create"
    assert entry["outcome"] == "success"
    assert entry["status"] == 201
    assert entry["duration_ms"] >= 0
    assert re.fullmatch(r"[0-9a-f]{32}", entry["trace_id"])
    assert re.fullmatch(r"[0-9a-f]{16}", entry["span_id"])

    # The OTLP record is tied to the same trace, so Loki links to Tempo.
    assert format(record.log_record.trace_id, "032x") == entry["trace_id"]
    assert record.log_record.attributes["journey.outcome"] == "success"

    # The request's server span has that trace_id.
    server = [s for s in spans.get_finished_spans() if s.name == "POST /projects"]
    assert server, [s.name for s in spans.get_finished_spans()]
    assert {format(s.context.trace_id, "032x") for s in server} == {entry["trace_id"]}

    # And the latency metric's exemplar carries it too.
    data = metrics.get_metrics_data()
    exemplar_ids = {
        format(e.trace_id, "032x")
        for rm in data.resource_metrics
        for sm in rm.scope_metrics
        for m in sm.metrics
        if m.name == "projects_create_latency_ms"
        for p in m.data.data_points
        for e in p.exemplars
        if e.trace_id
    }
    assert entry["trace_id"] in exemplar_ids


def test_log_line_has_no_email_credentials_or_body(telemetry) -> None:
    client, _spans, _metrics, logs = telemetry
    headers = _headers(client)
    client.post(
        "/projects", json={"name": "Secret plan", "pitch": EMAIL}, headers=headers
    )
    (record,) = _journey_lines(logs)
    body = str(record.log_record.body)
    assert not EMAIL_RE.search(body)
    assert "Secret plan" not in body
    assert TEST_PASSWORD not in body
    assert "Bearer" not in body
    assert set(_entry(record)) == {
        "event",
        "outcome",
        "status",
        "duration_ms",
        "trace_id",
        "span_id",
    }
    attributes = " ".join(str(v) for v in record.log_record.attributes.values())
    assert not EMAIL_RE.search(attributes)


def test_client_errors_are_logged_with_their_outcome(telemetry) -> None:
    client, _spans, _metrics, logs = telemetry
    assert client.post("/projects", json={"name": "x"}).status_code == 401
    (record,) = _journey_lines(logs)
    assert _entry(record)["outcome"] == "client_error"
    assert _entry(record)["status"] == 401


def test_only_project_creation_is_logged(telemetry) -> None:
    client, _spans, _metrics, logs = telemetry
    headers = _headers(client)
    client.get("/projects", headers=headers)
    assert _journey_lines(logs) == []


def test_logs_to_stdout_without_telemetry(
    store: Store, caplog: pytest.LogCaptureFixture
) -> None:
    app = FastAPI()
    app.include_router(auth.router)
    app.include_router(projects.router)
    app.add_middleware(JourneyLogMiddleware)
    app.dependency_overrides[get_store] = lambda: store
    with caplog.at_level(logging.INFO, logger="app.projects"):
        with TestClient(app) as client:
            client.post("/projects", json={"name": "x"})
    (line,) = [r.getMessage() for r in caplog.records if r.name == "app.projects"]
    entry = json.loads(line.split(" ", 1)[1])
    # No span without telemetry: the ids are null, not invented.
    assert entry["trace_id"] is None
    assert entry["outcome"] == "client_error"


@pytest.mark.parametrize(
    "status, expected",
    [
        (201, "success"),
        (403, "client_error"),
        (422, "client_error"),
        (500, "server_error"),
    ],
)
def test_outcome(status: int, expected: str) -> None:
    assert outcome(status) == expected


def test_injected_5xx_is_a_server_error_with_the_alert_labels(
    telemetry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What the alert rule (infra/hub/grafana.tf) counts: the 500 lands in
    projects_create_errors_total with http.status_code and
    hub.environment, and the journey line says server_error."""
    from app.core import config

    client, _spans, metrics, logs = telemetry
    headers = _headers(client)
    monkeypatch.setattr(config, "FAULT_INJECT_5XX", True)
    assert (
        client.post("/projects", json={"name": "x"}, headers=headers).status_code == 500
    )

    (record,) = _journey_lines(logs)
    assert _entry(record)["outcome"] == "server_error"
    assert record.log_record.severity_text == "WARN"

    data = metrics.get_metrics_data()
    points = {
        m.name: list(m.data.data_points)
        for rm in data.resource_metrics
        for sm in rm.scope_metrics
        for m in sm.metrics
    }
    (error,) = points["projects_create_errors_total"]
    assert dict(error.attributes) == {"hub.environment": "dev", "http.status_code": 500}
    (total,) = points["projects_create_total"]
    assert dict(total.attributes) == {"hub.environment": "dev"}

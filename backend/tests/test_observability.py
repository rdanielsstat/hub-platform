"""OpenTelemetry setup in observability/: resource attributes, exporter
wiring, HTTP and database spans, and the per-endpoint metrics.

Each test builds its own FastAPI app (with the real routers) and
passes in-memory exporters where it needs to read telemetry back, so
nothing here depends on, or leaks into, the process-wide app that
conftest imports (which runs with OTEL_SDK_DISABLED=true).
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.metrics.export import (
    InMemoryMetricReader,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from app.db import session as db_session
from app.db.store import Store, get_store
from app.routers import auth, health, notes, projects
from observability import initialize_observability
from observability.config import load_config
from observability.metrics import ENDPOINT_METRICS
from tests.conftest import TEST_PASSWORD

OPENAPI_PATH = Path(__file__).resolve().parents[2] / "openapi.yaml"

_OBSERVABILITY_VARS = (
    "SERVICE_VERSION",
    "LAMBDA_IMAGE_TAG",
    "ENVIRONMENT",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_HEADERS",
    "OTEL_SDK_DISABLED",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scrub every variable observability reads, so a developer's shell
    (or conftest's OTEL_SDK_DISABLED) can't change what these tests see."""
    for var in _OBSERVABILITY_VARS:
        monkeypatch.delenv(var, raising=False)


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(projects.router)
    app.include_router(notes.router)
    return app


@pytest.fixture()
def span_exporter() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture()
def metric_reader() -> InMemoryMetricReader:
    return InMemoryMetricReader()


@pytest.fixture()
def instrumented(
    store: Store,
    span_exporter: InMemorySpanExporter,
    metric_reader: InMemoryMetricReader,
) -> Iterator[TestClient]:
    app = _build_app()
    app.dependency_overrides[get_store] = lambda: store
    handle = initialize_observability(
        app, span_exporter=span_exporter, metric_reader=metric_reader
    )
    assert handle is not None
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        handle.shutdown()


def _metric_points(reader: InMemoryMetricReader) -> dict[str, list]:
    data = reader.get_metrics_data()
    points: dict[str, list] = {}
    if data is None:
        return points
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                points.setdefault(metric.name, []).extend(metric.data.data_points)
    return points


def _counter(reader: InMemoryMetricReader, name: str) -> int:
    return sum(p.value for p in _metric_points(reader).get(name, []))


def _histogram_count(reader: InMemoryMetricReader, name: str) -> int:
    return sum(p.count for p in _metric_points(reader).get(name, []))


def _login(client: TestClient, email: str) -> dict[str, str]:
    client.post("/auth/register", json={"email": email, "password": TEST_PASSWORD})
    res = client.post(
        "/auth/login", data={"username": email, "password": TEST_PASSWORD}
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


# ---- config and wiring ---------------------------------------------


def test_resource_attributes_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAMBDA_IMAGE_TAG", "abc123")
    monkeypatch.setenv("ENVIRONMENT", "prod")
    handle = initialize_observability(
        _build_app(),
        span_exporter=InMemorySpanExporter(),
        metric_reader=InMemoryMetricReader(),
    )
    assert handle is not None
    try:
        attrs = handle.tracer_provider.resource.attributes
        assert attrs["service.name"] == "hub-platform"
        assert attrs["service.version"] == "abc123"
        assert attrs["deployment.environment"] == "prod"
        # Metrics carry the same resource as traces.
        assert handle.meter_provider._sdk_config.resource.attributes == attrs
    finally:
        handle.shutdown()


def test_resource_attribute_defaults() -> None:
    config = load_config()
    assert config.service_name == "hub-platform"
    assert config.service_version == "local-dev"
    assert config.environment == "dev"


def test_service_version_from_service_version_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SERVICE_VERSION", "20260930-120000-abc1234")
    assert load_config().service_version == "20260930-120000-abc1234"


def test_service_version_wins_over_lambda_image_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SERVICE_VERSION", "from-service-version")
    monkeypatch.setenv("LAMBDA_IMAGE_TAG", "from-lambda-image-tag")
    assert load_config().service_version == "from-service-version"


def test_tracer_provider_uses_simple_span_processor() -> None:
    handle = initialize_observability(
        _build_app(), metric_reader=InMemoryMetricReader()
    )
    assert handle is not None
    try:
        assert isinstance(handle.span_processor, SimpleSpanProcessor)
        registered = handle.tracer_provider._active_span_processor._span_processors
        assert registered == (handle.span_processor,)
    finally:
        handle.shutdown()


def test_metric_reader_is_periodic_every_60s() -> None:
    handle = initialize_observability(
        _build_app(), span_exporter=InMemorySpanExporter()
    )
    assert handle is not None
    try:
        assert isinstance(handle.metric_reader, PeriodicExportingMetricReader)
        assert handle.metric_reader._export_interval_millis == 60_000
    finally:
        handle.shutdown()


def test_exporters_fall_back_to_local_collector(
    capsys: pytest.CaptureFixture[str],
) -> None:
    handle = initialize_observability(_build_app())
    assert handle is not None
    try:
        assert handle.config.target == "local"
        assert handle.span_exporter_endpoint == "http://localhost:4318/v1/traces"
        assert handle.metric_exporter_endpoint == "http://localhost:4318/v1/metrics"
        assert "http://localhost:4318" in capsys.readouterr().out
    finally:
        handle.shutdown()


def test_exporters_point_at_grafana_cloud(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    base = "https://otlp-gateway-prod-us-central-1.grafana.net/otlp"
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", base + "/")
    # Exactly as Grafana Cloud's OTLP setup page generates it.
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "Authorization=Basic%20s3cret")
    handle = initialize_observability(_build_app())
    assert handle is not None
    try:
        assert handle.config.target == "grafana"
        assert handle.config.headers == {"authorization": "Basic s3cret"}
        assert handle.span_exporter_endpoint == base + "/v1/traces"
        assert handle.metric_exporter_endpoint == base + "/v1/metrics"
        out = capsys.readouterr().out
        assert "Grafana Cloud" in out and base in out
        # The token must never end up in the logs.
        assert "s3cret" not in out
    finally:
        handle.shutdown()


def test_headers_without_authorization_warn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A bare token (no `Authorization=Basic%20` prefix) isn't a valid
    OTEL_EXPORTER_OTLP_HEADERS value; say so at startup, without
    echoing it."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://otlp.example/otlp")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "czNjcmV0Cg==")
    config = load_config()
    assert config.target == "grafana"
    assert "authorization" not in config.headers
    assert config.warning is not None
    assert "Authorization=Basic%20" in config.warning
    assert "czNjcmV0Cg" not in config.warning


def test_headers_without_endpoint_fall_back_to_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "Authorization=Basic%20s3cret")
    config = load_config()
    assert config.target == "local"
    assert config.endpoint == "http://localhost:4318"
    assert config.headers == {}
    assert config.warning is not None and "s3cret" not in config.warning


def test_disabled_via_otel_sdk_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    assert initialize_observability(_build_app()) is None


def test_setup_failure_is_logged_not_raised(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import observability

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("collector config exploded")

    monkeypatch.setattr(observability, "_setup", boom)
    app = _build_app()
    assert initialize_observability(app) is None
    assert "collector config exploded" in capsys.readouterr().out
    # The app still serves requests.
    assert TestClient(app).get("/health").status_code == 200


# ---- spans ---------------------------------------------------------


def test_http_request_creates_server_span(
    instrumented: TestClient, span_exporter: InMemorySpanExporter
) -> None:
    assert instrumented.get("/health").status_code == 200
    server_spans = [
        s for s in span_exporter.get_finished_spans() if s.name == "GET /health"
    ]
    assert len(server_spans) == 1
    attrs = server_spans[0].attributes
    assert attrs["http.method"] == "GET"
    assert attrs["http.route"] == "/health"
    assert attrs["http.target"] == "/health"
    assert attrs["http.status_code"] == 200


def test_database_query_creates_span(
    monkeypatch: pytest.MonkeyPatch, span_exporter: InMemorySpanExporter
) -> None:
    """Uses the app's own lazily built engine (app/db/session.py), so
    this fails if that module binds create_engine before the SQLAlchemy
    instrumentation has patched it."""
    monkeypatch.setattr(db_session, "_engine", None)
    handle = initialize_observability(
        _build_app(),
        span_exporter=span_exporter,
        metric_reader=InMemoryMetricReader(),
    )
    assert handle is not None
    try:
        engine = db_session._get_engine()
        with engine.connect() as conn:
            conn.execute(sqlalchemy.text("SELECT 42"))
        engine.dispose()
    finally:
        handle.shutdown()
    statements = [
        s.attributes.get("db.statement") for s in span_exporter.get_finished_spans()
    ]
    assert "SELECT 42" in statements


# ---- metrics -------------------------------------------------------


def test_every_openapi_operation_has_endpoint_metrics() -> None:
    spec = yaml.safe_load(OPENAPI_PATH.read_text())
    operations = {
        (method.upper(), path)
        for path, item in spec["paths"].items()
        for method in item
        if method in {"get", "post", "put", "patch", "delete"}
    }
    assert set(ENDPOINT_METRICS) == operations
    names = list(ENDPOINT_METRICS.values())
    assert len(names) == len(set(names))


def test_request_increments_endpoint_counter_and_latency(
    instrumented: TestClient, metric_reader: InMemoryMetricReader
) -> None:
    name = ENDPOINT_METRICS[("GET", "/health")]
    instrumented.get("/health")
    instrumented.get("/health")
    assert _counter(metric_reader, f"{name}_total") == 2
    assert _counter(metric_reader, f"{name}_errors_total") == 0
    assert _histogram_count(metric_reader, f"{name}_latency_ms") == 2


def test_path_parameters_resolve_to_route_template(
    instrumented: TestClient, metric_reader: InMemoryMetricReader
) -> None:
    headers = _login(instrumented, "paths@example.com")
    instrumented.get("/projects/does-not-exist", headers=headers)
    name = ENDPOINT_METRICS[("GET", "/projects/{project_id}")]
    assert _counter(metric_reader, f"{name}_total") == 1
    assert _counter(metric_reader, f"{name}_errors_total") == 1


def test_4xx_increments_error_counter(
    instrumented: TestClient, metric_reader: InMemoryMetricReader
) -> None:
    assert instrumented.get("/auth/me").status_code == 401
    name = ENDPOINT_METRICS[("GET", "/auth/me")]
    assert _counter(metric_reader, f"{name}_total") == 1
    assert _counter(metric_reader, f"{name}_errors_total") == 1


def test_5xx_increments_error_counter(
    store: Store,
    span_exporter: InMemorySpanExporter,
    metric_reader: InMemoryMetricReader,
) -> None:
    app = _build_app()

    def broken_store() -> Store:
        raise RuntimeError("database is on fire")

    app.dependency_overrides[get_store] = broken_store
    handle = initialize_observability(
        app, span_exporter=span_exporter, metric_reader=metric_reader
    )
    assert handle is not None
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            # Log in against a working store first, then break it.
            app.dependency_overrides[get_store] = lambda: store
            headers = _login(client, "boom@example.com")
            app.dependency_overrides[get_store] = broken_store
            assert client.get("/projects", headers=headers).status_code == 500
    finally:
        handle.shutdown()
    name = ENDPOINT_METRICS[("GET", "/projects")]
    assert _counter(metric_reader, f"{name}_total") == 1
    assert _counter(metric_reader, f"{name}_errors_total") == 1
    assert _histogram_count(metric_reader, f"{name}_latency_ms") == 1


def test_auth_and_domain_counters(
    instrumented: TestClient, metric_reader: InMemoryMetricReader
) -> None:
    headers = _login(instrumented, "domain@example.com")
    # Duplicate signup and wrong password: both errors.
    instrumented.post(
        "/auth/register",
        json={"email": "domain@example.com", "password": TEST_PASSWORD},
    )
    instrumented.post(
        "/auth/login", data={"username": "domain@example.com", "password": "nope"}
    )
    res = instrumented.post("/projects", json={"name": "Hub"}, headers=headers)
    assert res.status_code == 201, res.text
    project_id = res.json()["id"]
    res = instrumented.post(
        f"/projects/{project_id}/notes", json={"body": "hi"}, headers=headers
    )
    assert res.status_code == 201, res.text

    assert _counter(metric_reader, "authentication_signup_total") == 2
    assert _counter(metric_reader, "authentication_signup_errors_total") == 1
    assert _counter(metric_reader, "accounts_created_total") == 1
    assert _counter(metric_reader, "authentication_login_total") == 2
    assert _counter(metric_reader, "authentication_login_errors_total") == 1
    assert _counter(metric_reader, "projects_created_total") == 1
    assert _counter(metric_reader, "notes_created_total") == 1


# ---- logs (EXPORTED_LOGGERS) ---------------------------------------

from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter  # noqa: E402

from app.routers import errors  # noqa: E402
from observability import EXPORTED_LOGGERS  # noqa: E402


@pytest.fixture()
def log_exporter() -> InMemoryLogRecordExporter:
    return InMemoryLogRecordExporter()


@pytest.fixture()
def instrumented_with_logs(
    store: Store,
    span_exporter: InMemorySpanExporter,
    metric_reader: InMemoryMetricReader,
    log_exporter: InMemoryLogRecordExporter,
) -> Iterator[TestClient]:
    app = _build_app()
    app.include_router(errors.router)
    app.dependency_overrides[get_store] = lambda: store
    handle = initialize_observability(
        app,
        span_exporter=span_exporter,
        metric_reader=metric_reader,
        log_exporter=log_exporter,
    )
    assert handle is not None
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        handle.shutdown()


def test_client_error_reports_are_exported_as_otlp_logs(
    instrumented_with_logs: TestClient, log_exporter: InMemoryLogRecordExporter
) -> None:
    res = instrumented_with_logs.post(
        "/client-errors",
        json={"kind": "http", "message": "GET /projects returned 503", "status": 503},
    )

    assert res.status_code == 204
    (record,) = [
        r for r in log_exporter.get_finished_logs()
        if "client_error" in str(r.log_record.body)
    ]
    assert "GET /projects returned 503" in str(record.log_record.body)
    assert record.log_record.severity_text == "WARN"
    assert record.log_record.attributes["client_error.kind"] == "http"
    assert record.log_record.attributes["client_error.status"] == 503
    assert record.resource.attributes["service.name"] == "hub-platform"


def test_only_the_listed_loggers_are_exported(
    instrumented_with_logs: TestClient, log_exporter: InMemoryLogRecordExporter
) -> None:
    import logging

    logging.getLogger("app.db").warning("database_unavailable method=GET path=/x error=E")
    logging.getLogger("app.somewhere_else").warning("not exported")
    logging.getLogger("app.client_errors").info("below WARNING, not exported")

    bodies = [str(r.log_record.body) for r in log_exporter.get_finished_logs()]
    assert any("database_unavailable" in b for b in bodies)
    assert not any("not exported" in b for b in bodies)


def test_exported_loggers_list() -> None:
    assert EXPORTED_LOGGERS == ("app.client_errors", "app.db", "app.security")


def test_shutdown_removes_the_log_handler(
    store: Store,
    span_exporter: InMemorySpanExporter,
    metric_reader: InMemoryMetricReader,
    log_exporter: InMemoryLogRecordExporter,
) -> None:
    import logging

    handle = initialize_observability(
        _build_app(),
        span_exporter=span_exporter,
        metric_reader=metric_reader,
        log_exporter=log_exporter,
    )
    assert handle is not None
    handle.shutdown()

    for name in EXPORTED_LOGGERS:
        assert handle.log_handler not in logging.getLogger(name).handlers


def test_disabled_observability_attaches_no_log_handler() -> None:
    import logging

    from opentelemetry.instrumentation.logging.handler import LoggingHandler

    initialize_observability(_build_app(), enabled=False)

    for name in EXPORTED_LOGGERS:
        assert not any(
            isinstance(h, LoggingHandler) for h in logging.getLogger(name).handlers
        )


def test_report_without_status_exports_cleanly(
    instrumented_with_logs: TestClient, log_exporter: InMemoryLogRecordExporter
) -> None:
    instrumented_with_logs.post("/client-errors", json={"kind": "error", "message": "boom"})

    (record,) = [
        r for r in log_exporter.get_finished_logs()
        if "client_error" in str(r.log_record.body)
    ]
    assert record.log_record.attributes["client_error.kind"] == "error"
    assert "client_error.status" not in record.log_record.attributes


def test_log_handler_flush_starts_no_thread(
    store: Store,
    span_exporter: InMemorySpanExporter,
    metric_reader: InMemoryMetricReader,
    log_exporter: InMemoryLogRecordExporter,
) -> None:
    """logging.shutdown() flushes every handler at interpreter exit, when
    starting a thread raises; the handler's flush must not need one."""
    import threading

    handle = initialize_observability(
        _build_app(),
        span_exporter=span_exporter,
        metric_reader=metric_reader,
        log_exporter=log_exporter,
    )
    assert handle is not None
    try:
        before = threading.active_count()
        handle.log_handler.flush()
        assert threading.active_count() == before
    finally:
        handle.shutdown()

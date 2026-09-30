"""App-level metrics: per-endpoint request, error and latency instruments,
plus auth and domain counters, recorded by an ASGI middleware so route
handlers stay untouched.

Every operation in openapi.yaml has an entry in ENDPOINT_METRICS
(tests/test_observability.py keeps the two in sync). Each entry gets:

    {name}_total         counter, every request
    {name}_errors_total  counter, responses with status >= 400
    {name}_latency_ms    histogram, request duration in milliseconds
"""

import time
from dataclasses import dataclass

from opentelemetry.metrics import Counter, Histogram, Meter
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# (method, route template) -> metric name prefix.
ENDPOINT_METRICS: dict[tuple[str, str], str] = {
    ("GET", "/health"): "health_get",
    ("POST", "/auth/register"): "auth_register_post",
    ("POST", "/auth/login"): "auth_login_post",
    ("GET", "/auth/me"): "auth_me_get",
    ("GET", "/projects"): "projects_list",
    ("POST", "/projects"): "projects_create",
    ("GET", "/projects/{project_id}"): "project_get",
    ("PATCH", "/projects/{project_id}"): "project_update",
    ("DELETE", "/projects/{project_id}"): "project_delete",
    ("GET", "/projects/{project_id}/notes"): "project_notes_list",
    ("POST", "/projects/{project_id}/notes"): "project_notes_create",
    ("DELETE", "/notes/{note_id}"): "note_delete",
}

_SIGNUP = ("POST", "/auth/register")
_LOGIN = ("POST", "/auth/login")
_CREATE_PROJECT = ("POST", "/projects")
_CREATE_NOTE = ("POST", "/projects/{project_id}/notes")


@dataclass(frozen=True)
class _EndpointInstruments:
    total: Counter
    errors: Counter
    latency_ms: Histogram


class HttpMetrics:
    """Creates every instrument up front and records one request at a time."""

    def __init__(self, meter: Meter) -> None:
        self._endpoints = {
            key: _EndpointInstruments(
                total=meter.create_counter(f"{name}_total", unit="1"),
                errors=meter.create_counter(f"{name}_errors_total", unit="1"),
                latency_ms=meter.create_histogram(f"{name}_latency_ms", unit="ms"),
            )
            for key, name in ENDPOINT_METRICS.items()
        }
        self._login_total = meter.create_counter("authentication_login_total")
        self._login_errors = meter.create_counter("authentication_login_errors_total")
        self._signup_total = meter.create_counter("authentication_signup_total")
        self._signup_errors = meter.create_counter("authentication_signup_errors_total")
        self._accounts_created = meter.create_counter("accounts_created_total")
        self._projects_created = meter.create_counter("projects_created_total")
        self._notes_created = meter.create_counter("notes_created_total")

    def record(self, method: str, route: str, status: int, duration_ms: float) -> None:
        key = (method, route)
        instruments = self._endpoints.get(key)
        if instruments is None:
            return
        failed = status >= 400
        instruments.total.add(1)
        instruments.latency_ms.record(duration_ms)
        if failed:
            instruments.errors.add(1, {"http.status_code": status})

        if key == _SIGNUP:
            self._signup_total.add(1)
            if failed:
                self._signup_errors.add(1)
            else:
                self._accounts_created.add(1)
        elif key == _LOGIN:
            self._login_total.add(1)
            if failed:
                self._login_errors.add(1)
        elif key == _CREATE_PROJECT and not failed:
            self._projects_created.add(1)
        elif key == _CREATE_NOTE and not failed:
            self._notes_created.add(1)


class MetricsMiddleware:
    """Times each HTTP request and hands it to HttpMetrics once routing
    has resolved the route template (FastAPI stores the matched route in
    the shared ASGI scope)."""

    def __init__(self, app: ASGIApp, metrics: HttpMetrics) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Stays 500 if the app raises before sending a response.
        status = 500

        async def send_with_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        start = time.perf_counter()
        try:
            await self.app(scope, receive, send_with_status)
        finally:
            route = getattr(scope.get("route"), "path", None)
            if route is not None:
                duration_ms = (time.perf_counter() - start) * 1000
                try:
                    self.metrics.record(scope["method"], route, status, duration_ms)
                except Exception:  # noqa: BLE001
                    # Metrics must never turn into a failed request.
                    pass

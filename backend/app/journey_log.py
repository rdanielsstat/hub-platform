"""The project creation journey: one structured log line per
POST /projects request.

Each line is a JSON object on the "app.projects" logger with the
outcome, the status, the duration and the request's trace_id and
span_id, so a line in Loki (or CloudWatch) leads straight to its trace
in Tempo and to the projects_create_* metrics, whose latency exemplar
carries the same trace_id (observability/). Nothing from the request
goes in: no body, no email, no token, no user id.

Wherever OTEL_ENABLED is on, observability/ also exports this logger at
INFO as OTLP log records (EXPORTED_INFO_LOGGERS). It prints to stdout
either way, which CloudWatch keeps when deployed.
"""

import json
import logging
import sys
import time

from opentelemetry import trace
from starlette.types import ASGIApp, Message, Receive, Scope, Send

ROUTE = ("POST", "/projects")

logger = logging.getLogger("app.projects")
logger.setLevel(logging.INFO)
if not any(getattr(h, "_hub_stdout", False) for h in logger.handlers):
    # Nothing else configures a handler for app loggers, and the
    # fallback one only prints WARNING and above.
    _stdout = logging.StreamHandler(sys.stdout)
    _stdout._hub_stdout = True  # type: ignore[attr-defined]
    logger.addHandler(_stdout)


def outcome(status: int) -> str:
    if status >= 500:
        return "server_error"
    if status >= 400:
        return "client_error"
    return "success"


def _trace_ids() -> tuple[str | None, str | None]:
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None, None
    return format(context.trace_id, "032x"), format(context.span_id, "016x")


class JourneyLogMiddleware:
    """Logs one line per POST /projects once the response is known.
    Runs inside the OpenTelemetry request span (the FastAPI
    instrumentation always wraps the whole middleware stack), so the
    current span is the request's."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

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
            if (scope["method"], route) == ROUTE:
                try:
                    _log(status, (time.perf_counter() - start) * 1000)
                except Exception:  # noqa: BLE001
                    # Logging must never turn into a failed request.
                    pass


def _log(status: int, duration_ms: float) -> None:
    trace_id, span_id = _trace_ids()
    entry = {
        "event": "project_create",
        "outcome": outcome(status),
        "status": status,
        "duration_ms": round(duration_ms, 1),
        "trace_id": trace_id,
        "span_id": span_id,
    }
    # extra becomes OTLP log attributes (None isn't allowed there).
    attributes: dict[str, str | int] = {
        "journey": "project_create",
        "journey.outcome": entry["outcome"],
        "http.status_code": status,
    }
    level = logging.WARNING if status >= 500 else logging.INFO
    logger.log(level, "project_create %s", json.dumps(entry), extra=attributes)

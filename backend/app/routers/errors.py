"""Frontend error reports: POST /client-errors.

The web app (frontend/src/lib/error-reporting.ts) sends one report per
uncaught JS error, unhandled promise rejection, React render crash, and
failed API call (network error or 5xx). Each becomes one JSON log line
on the "app.client_errors" logger: CloudWatch Logs when deployed, the
console locally, and, wherever OTEL_ENABLED is on, Grafana Cloud as an
OTLP log record (observability/, EXPORTED_LOGGERS; stored in Loki). The
request also shows up in the per-endpoint metrics as client_errors_post_*.

Unauthenticated on purpose: errors happen while signed out too (the
login page can crash). So it's rate limited per client IP
(CLIENT_ERROR_RATE_LIMIT_PER_MINUTE), every field is length-capped, and
nothing in a report is trusted or echoed back. When the request does
carry a valid session, the user id (never the email) is attached so a
report can be tied to an account. URLs lose their query string and
fragment before logging; see security/DATA_POLICY.md.
"""

import json
import logging
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, Request, status
from pydantic import Field

from app.auth.rate_limit import limit_client_error_reports
from app.auth.security import decode_access_token
from app.core.config import AUTH_COOKIE_NAME
from app.models.base import CamelModel

logger = logging.getLogger("app.client_errors")

router = APIRouter(tags=["errors"])


class ClientErrorReport(CamelModel):
    kind: Literal["error", "unhandledrejection", "render", "http"]
    message: str = Field(max_length=2000)
    stack: str | None = Field(default=None, max_length=8000)
    # The page the error happened on.
    url: str | None = Field(default=None, max_length=2000)
    user_agent: str | None = Field(default=None, max_length=500)
    # kind == "http" only: the failed call. status 0 means no response at
    # all (network error, CORS, the backend unreachable).
    endpoint: str | None = Field(default=None, max_length=500)
    method: str | None = Field(default=None, max_length=10)
    status: int | None = Field(default=None, ge=0, le=599)


def _strip_query(url: str | None) -> str | None:
    """Drop the query string and fragment: they're where anything
    sensitive in a URL would be."""
    if not url:
        return url
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _user_id(request: Request) -> str | None:
    """The signed-in user's id, if the request carries a valid token.
    Signature and expiry only, no database lookup: this endpoint must
    keep working when the database is the thing that's broken."""
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else None
    token = token or request.cookies.get(AUTH_COOKIE_NAME)
    return decode_access_token(token) if token else None


@router.post(
    "/client-errors",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(limit_client_error_reports)],
)
def report_client_error(report: ClientErrorReport, request: Request) -> None:
    entry = report.model_dump()
    entry["url"] = _strip_query(report.url)
    entry["endpoint"] = _strip_query(report.endpoint)
    entry["user_id"] = _user_id(request)
    # One JSON object per line, so a log pipeline (CloudWatch Logs
    # Insights, Loki) can parse fields without a custom pattern.
    # extra becomes OTLP log attributes when the record is exported to
    # Grafana (observability/), so reports can be filtered by kind there.
    # (OTLP attributes can't be None, hence status only when present.)
    attributes: dict[str, str | int] = {"client_error.kind": report.kind}
    if report.status is not None:
        attributes["client_error.status"] = report.status
    logger.warning(
        "client_error %s", json.dumps(entry, sort_keys=True), extra=attributes
    )

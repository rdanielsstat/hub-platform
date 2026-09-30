"""Observability settings, read from environment variables.

Every variable is optional. The two OTLP ones are the standard
OpenTelemetry variables, pasted as-is from Grafana Cloud's OTLP setup
page. Without an endpoint, telemetry goes to a local OTLP/HTTP collector
on localhost:4318.

    OTEL_EXPORTER_OTLP_ENDPOINT  OTLP/HTTP base URL, e.g.
                                 https://otlp-gateway-prod-us-central-1.grafana.net/otlp
    OTEL_EXPORTER_OTLP_HEADERS   Comma-separated key=value pairs, values
                                 URL-encoded, e.g.
                                 Authorization=Basic%20<base64 token>
    SERVICE_VERSION              service.version; the dev Lambda gets its
                                 image tag here (infra/hub).
    LAMBDA_IMAGE_TAG             service.version if SERVICE_VERSION is
                                 unset (default "local-dev").
    ENVIRONMENT                  deployment.environment (default "dev").
    OTEL_SDK_DISABLED            "true" turns observability off entirely.
"""

import os
from dataclasses import dataclass, field
from typing import Literal

from opentelemetry.util.re import parse_env_headers

SERVICE_NAME = "hub-platform"
LOCAL_OTLP_ENDPOINT = "http://localhost:4318"


@dataclass(frozen=True)
class ObservabilityConfig:
    service_name: str
    service_version: str
    environment: str
    # Base OTLP/HTTP URL; the exporters append /v1/traces and /v1/metrics.
    endpoint: str
    target: Literal["grafana", "local"]
    headers: dict[str, str] = field(default_factory=dict, repr=False)
    disabled: bool = False
    # Set when the OTLP settings are only half there, so startup can
    # say why it fell back or sent unauthenticated requests.
    warning: str | None = None


def load_config() -> ObservabilityConfig:
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip().rstrip("/")
    raw_headers = os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "").strip()

    warning = None
    if endpoint:
        target: Literal["grafana", "local"] = "grafana"
        # Header names come back lowercased, values URL-decoded. Never
        # log these: they carry the credential.
        headers = dict(parse_env_headers(raw_headers, liberal=True))
        if "authorization" not in headers:
            warning = (
                "OTEL_EXPORTER_OTLP_HEADERS has no Authorization header; "
                "expected the form Authorization=Basic%20<token>. Exporting without auth"
            )
    else:
        target, endpoint, headers = "local", LOCAL_OTLP_ENDPOINT, {}
        if raw_headers:
            warning = "OTEL_EXPORTER_OTLP_HEADERS is set but OTEL_EXPORTER_OTLP_ENDPOINT is not; using the local collector"

    return ObservabilityConfig(
        service_name=SERVICE_NAME,
        service_version=(
            os.environ.get("SERVICE_VERSION")
            or os.environ.get("LAMBDA_IMAGE_TAG")
            or "local-dev"
        ),
        environment=os.environ.get("ENVIRONMENT") or "dev",
        endpoint=endpoint,
        target=target,
        headers=headers,
        disabled=os.environ.get("OTEL_SDK_DISABLED", "").strip().lower() == "true",
        warning=warning,
    )

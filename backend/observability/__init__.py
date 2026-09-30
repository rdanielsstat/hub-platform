"""OpenTelemetry setup for the Hub API: traces and metrics over OTLP/HTTP
to Grafana Cloud, or to a local collector when Grafana isn't configured
(see config.py).

Call initialize_observability(app, enabled=...) once, right after
creating the FastAPI app; app/main.py passes the OTEL_ENABLED setting. It never raises: a bad config or unreachable collector
is reported and the app carries on without (or with degraded)
telemetry.
"""

import time
from collections.abc import Sequence
from dataclasses import dataclass

from fastapi import FastAPI
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)

from observability.config import ObservabilityConfig, load_config
from observability.metrics import HttpMetrics, MetricsMiddleware

__all__ = ["initialize_observability"]

METRIC_EXPORT_INTERVAL_MS = 60_000
# SimpleSpanProcessor exports inside the request, so a slow or dead
# collector would otherwise add its full timeout to every request.
_SPAN_EXPORT_TIMEOUT_S = 2
_SPAN_EXPORT_COOLDOWN_S = 60
_METRIC_EXPORT_TIMEOUT_S = 5
_SHUTDOWN_FLUSH_TIMEOUT_MS = 5_000


def _log(message: str) -> None:
    # print, not logging, to match app/core/config.py: nothing configures
    # a handler for app loggers, so INFO lines would be dropped. flush so
    # it shows up promptly when stdout isn't a TTY.
    print(f"observability: {message}", flush=True)


@dataclass
class Observability:
    """What initialize_observability() built, for tests and shutdown."""

    app: FastAPI
    config: ObservabilityConfig
    tracer_provider: TracerProvider
    meter_provider: MeterProvider
    span_processor: SimpleSpanProcessor
    metric_reader: MetricReader
    # None when the caller supplied its own exporter/reader.
    span_exporter_endpoint: str | None
    metric_exporter_endpoint: str | None

    def flush(self) -> None:
        try:
            self.tracer_provider.force_flush(_SHUTDOWN_FLUSH_TIMEOUT_MS)
            self.metric_reader.force_flush(_SHUTDOWN_FLUSH_TIMEOUT_MS)
        except Exception as exc:  # noqa: BLE001
            _log(f"WARNING: flushing telemetry failed: {exc!r}")

    def shutdown(self) -> None:
        """Undo the global instrumentation and stop the providers. The
        app itself uses flush() on shutdown instead; this is for tests."""
        SQLAlchemyInstrumentor().uninstrument()
        FastAPIInstrumentor.uninstrument_app(self.app)
        self.tracer_provider.shutdown()
        self.meter_provider.shutdown()


class _FailFastSpanExporter(SpanExporter):
    """After a failed export, drops spans for a cooldown period instead
    of retrying on every request, and warns once per failure."""

    def __init__(self, inner: SpanExporter, endpoint: str) -> None:
        self._inner = inner
        self._endpoint = endpoint
        self._skip_until = 0.0

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        now = time.monotonic()
        if now < self._skip_until:
            return SpanExportResult.FAILURE
        result = self._inner.export(spans)
        if result is not SpanExportResult.SUCCESS:
            self._skip_until = now + _SPAN_EXPORT_COOLDOWN_S
            _log(
                f"WARNING: span export to {self._endpoint} failed; dropping "
                f"spans for {_SPAN_EXPORT_COOLDOWN_S}s"
            )
        return result

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return self._inner.force_flush(timeout_millis)


def initialize_observability(
    app: FastAPI,
    *,
    enabled: bool = True,
    span_exporter: SpanExporter | None = None,
    metric_reader: MetricReader | None = None,
) -> Observability | None:
    """Instrument `app` (and SQLAlchemy) and start exporting telemetry.

    span_exporter / metric_reader replace the OTLP ones; tests pass
    in-memory versions. Returns None when disabled or when setup fails.
    enabled=False skips everything: no instrumentation, no exporters.
    """
    if not enabled:
        _log("disabled")
        return None
    try:
        config = load_config()
        if config.disabled:
            _log("disabled (OTEL_SDK_DISABLED=true)")
            return None
        return _setup(app, config, span_exporter, metric_reader)
    except Exception as exc:  # noqa: BLE001
        _log(f"WARNING: setup failed, continuing without telemetry: {exc!r}")
        return None


def _setup(
    app: FastAPI,
    config: ObservabilityConfig,
    span_exporter: SpanExporter | None,
    metric_reader: MetricReader | None,
) -> Observability:
    if config.warning:
        _log(f"WARNING: {config.warning}")

    resource = Resource.create(
        {
            "service.name": config.service_name,
            "service.version": config.service_version,
            "deployment.environment": config.environment,
        }
    )

    span_endpoint = None
    if span_exporter is None:
        span_endpoint = f"{config.endpoint}/v1/traces"
        span_exporter = _FailFastSpanExporter(
            OTLPSpanExporter(
                endpoint=span_endpoint,
                headers=config.headers,
                timeout=_SPAN_EXPORT_TIMEOUT_S,
            ),
            span_endpoint,
        )
    # Simple, not Batch: Lambda freezes the process as soon as the
    # handler returns, so a background batch might never be sent.
    span_processor = SimpleSpanProcessor(span_exporter)
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(span_processor)

    metric_endpoint = None
    if metric_reader is None:
        metric_endpoint = f"{config.endpoint}/v1/metrics"
        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(
                endpoint=metric_endpoint,
                headers=config.headers,
                timeout=_METRIC_EXPORT_TIMEOUT_S,
            ),
            export_interval_millis=METRIC_EXPORT_INTERVAL_MS,
        )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        # One span per request, not three: every span is a synchronous
        # export under SimpleSpanProcessor.
        exclude_spans=["receive", "send"],
    )
    SQLAlchemyInstrumentor().instrument(
        tracer_provider=tracer_provider, meter_provider=meter_provider
    )
    app.add_middleware(
        MetricsMiddleware,
        metrics=HttpMetrics(meter_provider.get_meter("observability")),
    )

    handle = Observability(
        app=app,
        config=config,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        span_processor=span_processor,
        metric_reader=metric_reader,
        span_exporter_endpoint=span_endpoint,
        metric_exporter_endpoint=metric_endpoint,
    )
    # Runs at the end of every Lambda invocation (Mangum drives the
    # lifespan per event) and on uvicorn shutdown, so metrics recorded
    # since the last 60s tick aren't lost when the process freezes.
    app.router.add_event_handler("shutdown", handle.flush)

    if "grafana.net" in config.endpoint:
        where = "Grafana Cloud"
    elif "localhost" in config.endpoint:
        where = "local collector"
    else:
        where = config.endpoint
    _log(
        f"exporting traces and metrics to {where} at {config.endpoint} "
        f"(service.version={config.service_version}, "
        f"deployment.environment={config.environment})"
    )
    return handle

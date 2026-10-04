"""OpenTelemetry setup for the Hub API: traces, metrics and selected logs
over OTLP/HTTP to Grafana Cloud, or to a local collector when Grafana isn't
configured (see config.py).

Logs: only the loggers in EXPORTED_LOGGERS (frontend error reports,
database outages, origin-verification rejections) are exported, as OTLP
log records that Grafana Cloud stores in Loki. They still go to stdout
(CloudWatch) exactly as before; the OTLP handler is added alongside.

Call initialize_observability(app, enabled=...) once, right after
creating the FastAPI app; app/main.py passes the OTEL_ENABLED setting. It never raises: a bad config or unreachable collector
is reported and the app carries on without (or with degraded)
telemetry.
"""

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field

from fastapi import FastAPI
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, ReadableLogRecord
from opentelemetry.sdk._logs.export import (
    LogRecordExporter,
    LogRecordExportResult,
    SimpleLogRecordProcessor,
)
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

__all__ = ["EXPORTED_LOGGERS", "initialize_observability"]

METRIC_EXPORT_INTERVAL_MS = 60_000

# App loggers whose WARNING-and-above records are exported as OTLP logs:
# frontend error reports (app/routers/errors.py), database outages
# (app/main.py) and origin-verification rejections (app/auth/origin_verify.py).
# Deliberately a short list: each record is exported synchronously.
EXPORTED_LOGGERS = ("app.client_errors", "app.db", "app.security")
# SimpleSpanProcessor exports inside the request, so a slow or dead
# collector would otherwise add its full timeout to every request.
_SPAN_EXPORT_TIMEOUT_S = 2
_SPAN_EXPORT_COOLDOWN_S = 60
_LOG_EXPORT_TIMEOUT_S = 2
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
    logger_provider: LoggerProvider
    log_handler: LoggingHandler
    # None when the caller supplied its own exporter/reader.
    span_exporter_endpoint: str | None
    metric_exporter_endpoint: str | None
    log_exporter_endpoint: str | None = None
    exported_loggers: tuple[str, ...] = field(default=EXPORTED_LOGGERS)

    def flush(self) -> None:
        try:
            self.tracer_provider.force_flush(_SHUTDOWN_FLUSH_TIMEOUT_MS)
            self.metric_reader.force_flush(_SHUTDOWN_FLUSH_TIMEOUT_MS)
            self.logger_provider.force_flush(_SHUTDOWN_FLUSH_TIMEOUT_MS)
        except Exception as exc:  # noqa: BLE001
            _log(f"WARNING: flushing telemetry failed: {exc!r}")

    def shutdown(self) -> None:
        """Undo the global instrumentation and stop the providers. The
        app itself uses flush() on shutdown instead; this is for tests."""
        SQLAlchemyInstrumentor().uninstrument()
        FastAPIInstrumentor.uninstrument_app(self.app)
        for name in self.exported_loggers:
            logging.getLogger(name).removeHandler(self.log_handler)
        self.tracer_provider.shutdown()
        self.meter_provider.shutdown()
        self.logger_provider.shutdown()


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


class _ExportOnEmitLoggingHandler(LoggingHandler):
    """The OTel handler, minus its flush().

    logging calls flush() on every handler at interpreter exit, and the
    base class flushes on a new thread, which Python refuses at that point
    ("can't create new thread at interpreter shutdown", printed as a
    traceback on every uvicorn shutdown). There's nothing to flush anyway:
    SimpleLogRecordProcessor exports each record as it's logged, and
    Observability.flush() still force-flushes the provider at the end of
    every Lambda invocation."""

    def flush(self) -> None:
        return None


class _FailFastLogExporter(LogRecordExporter):
    """The log counterpart of _FailFastSpanExporter: after a failed
    export, drops records for a cooldown instead of waiting out the
    timeout on every request that logs."""

    def __init__(self, inner: LogRecordExporter, endpoint: str) -> None:
        self._inner = inner
        self._endpoint = endpoint
        self._skip_until = 0.0

    def export(self, batch: Sequence[ReadableLogRecord]) -> LogRecordExportResult:
        now = time.monotonic()
        if now < self._skip_until:
            return LogRecordExportResult.FAILURE
        try:
            result = self._inner.export(batch)
        except Exception:  # noqa: BLE001
            result = LogRecordExportResult.FAILURE
        if result is not LogRecordExportResult.SUCCESS:
            self._skip_until = now + _SPAN_EXPORT_COOLDOWN_S
            _log(
                f"WARNING: log export to {self._endpoint} failed; dropping "
                f"logs for {_SPAN_EXPORT_COOLDOWN_S}s"
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
    log_exporter: LogRecordExporter | None = None,
) -> Observability | None:
    """Instrument `app` (and SQLAlchemy) and start exporting telemetry.

    span_exporter / metric_reader / log_exporter replace the OTLP ones;
    tests pass in-memory versions. Returns None when disabled or when setup fails.
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
        return _setup(app, config, span_exporter, metric_reader, log_exporter)
    except Exception as exc:  # noqa: BLE001
        _log(f"WARNING: setup failed, continuing without telemetry: {exc!r}")
        return None


def _setup(
    app: FastAPI,
    config: ObservabilityConfig,
    span_exporter: SpanExporter | None,
    metric_reader: MetricReader | None,
    log_exporter: LogRecordExporter | None = None,
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

    log_endpoint = None
    if log_exporter is None:
        log_endpoint = f"{config.endpoint}/v1/logs"
        log_exporter = _FailFastLogExporter(
            OTLPLogExporter(
                endpoint=log_endpoint,
                headers=config.headers,
                timeout=_LOG_EXPORT_TIMEOUT_S,
            ),
            log_endpoint,
        )
    # Simple, for the same Lambda-freeze reason as spans.
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(SimpleLogRecordProcessor(log_exporter))
    log_handler = _ExportOnEmitLoggingHandler(
        level=logging.WARNING, logger_provider=logger_provider
    )
    for name in EXPORTED_LOGGERS:
        logging.getLogger(name).addHandler(log_handler)

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
        logger_provider=logger_provider,
        log_handler=log_handler,
        log_exporter_endpoint=log_endpoint,
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
        f"exporting traces, metrics and logs to {where} at {config.endpoint} "
        f"(service.version={config.service_version}, "
        f"deployment.environment={config.environment})"
    )
    return handle

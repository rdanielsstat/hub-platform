# Local observability stack

A throwaway stack for checking instrumentation changes on your machine:
OpenTelemetry Collector, Tempo (traces), Prometheus (metrics), Loki
(logs) and Grafana. It's separate from the app stack in the repo-root
`docker-compose.yml`. Start it when you need it and shut it down after.

> **Local only.** Use this stack for test traffic. Never send test data
> to Grafana Cloud: before starting the backend against this stack,
> make sure `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_EXPORTER_OTLP_HEADERS`
> are not set to your Grafana Cloud values (check your shell, and don't
> pass an `--env-file` that contains them).

## Start

From `backend/`:

```
docker compose -f observability/docker-compose.yml up
```

Add `-d` to run it in the background.

| Service        | URL                     | Purpose                         |
| -------------- | ----------------------- | ------------------------------- |
| Grafana        | http://localhost:3000   | Dashboards and Explore          |
| OTel Collector | http://localhost:4318   | OTLP/HTTP in, from the backend  |
| Prometheus     | http://localhost:9090   | Metrics (scrapes the collector) |
| Loki           | http://localhost:3100   | Logs                            |
| Tempo          | http://localhost:3200   | Traces                          |

All ports are bound to `127.0.0.1`, so nothing is reachable from the
network.

## Grafana

Open http://localhost:3000 and log in with `admin` / `admin` (set
`GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` before `up` to change
them). Prometheus, Loki and Tempo are already configured as data
sources. Use **Explore** to query them:

- Metrics: e.g. `health_get_total`, `projects_create_errors_total`,
  `rate(health_get_latency_ms_count[5m])` (names as defined in
  `metrics.py`)
- Traces: Tempo, search by service name `hub-platform`

Metrics are exported every 60 seconds (and on backend shutdown), then
scraped every 15 seconds, so give them a minute to appear. Traces show
up almost immediately.

## Point the backend at it

Observability is off unless `OTEL_ENABLED=true`. With it on and
`OTEL_EXPORTER_OTLP_ENDPOINT` unset, the backend exports to
`http://localhost:4318`, so from `backend/`:

```
OTEL_ENABLED=true uv run uvicorn app.main:app --reload
```

At startup the backend prints
`observability: exporting traces and metrics to local collector at http://localhost:4318`.

## Stop

```
docker compose -f observability/docker-compose.yml down
```

Add `-v` to also delete stored traces (the `tempo-data` volume).

# Monitoring

What telemetry exists, where it goes, and how to look at it.

## Where everything goes

| Signal | Source | Dev | Prod | Local |
|---|---|---|---|---|
| Traces | OpenTelemetry (FastAPI + SQLAlchemy instrumentation) | Grafana Cloud (Tempo) | Grafana Cloud (Tempo) | Off, or the local stack |
| Metrics | OpenTelemetry (`backend/observability/metrics.py`) | Grafana Cloud (Prometheus/Mimir) | Grafana Cloud | Off, or the local stack |
| App logs | Python logging, stdout | CloudWatch Logs, 14 days | CloudWatch Logs, 14 days | Terminal |
| Frontend error reports | `POST /client-errors`, logged by the backend | CloudWatch Logs and Grafana Cloud (Loki) | CloudWatch Logs and Grafana Cloud (Loki) | Terminal, or the local stack |
| Database outages, rejected direct API calls | `app.db`, `app.security` loggers | CloudWatch Logs and Grafana Cloud (Loki) | same | Terminal |
| Bootstrap logs | stdout of the bootstrap Lambda | CloudWatch Logs, 14 days | CloudWatch Logs, 14 days | `docker compose logs bootstrap` |
| API Gateway and CloudFront | AWS | CloudWatch metrics (default) | same | n/a |

Telemetry export is on only where `OTEL_ENABLED` is set (the dev and prod
Lambdas, from OpenTofu). The OTLP endpoint and auth headers come from
GitHub secrets (`TF_VAR_otel_*_dev` in `ci.yml`, `TF_VAR_otel_*_prod` in
`promote.yml`), not SSM. Every trace and metric carries
`service.name=hub-platform` and `service.version` (`SERVICE_VERSION`,
from git tags).

## Metrics

From `backend/observability/metrics.py`. Every operation in
`openapi.yaml` gets three instruments (`tests/test_observability.py`
keeps the list in sync with the spec):

- `<name>_total`: requests
- `<name>_errors_total`: responses with status >= 400, labeled
  `http.status_code`
- `<name>_latency_ms`: duration histogram

| Operation | `<name>` |
|---|---|
| `GET /health` | `health_get` |
| `POST /auth/register` | `auth_register_post` |
| `POST /auth/login` | `auth_login_post` |
| `POST /auth/logout` | `auth_logout_post` |
| `GET /auth/me` | `auth_me_get` |
| `GET /projects` | `projects_list` |
| `POST /projects` | `projects_create` |
| `GET /projects/{project_id}` | `project_get` |
| `PATCH /projects/{project_id}` | `project_update` |
| `DELETE /projects/{project_id}` | `project_delete` |
| `GET /projects/{project_id}/notes` | `project_notes_list` |
| `POST /projects/{project_id}/notes` | `project_notes_create` |
| `DELETE /notes/{note_id}` | `note_delete` |
| `POST /client-errors` | `client_errors_post` |

Plus counters: `authentication_login_total`,
`authentication_login_errors_total`, `authentication_signup_total`,
`authentication_signup_errors_total`, `accounts_created_total`,
`projects_created_total`, `notes_created_total`.

Useful queries (Grafana Explore, Prometheus data source):

```
# Error ratio for one endpoint
rate(projects_create_errors_total[5m]) / rate(projects_create_total[5m])

# p95 latency of the session check (slow when Lambda or Neon are cold)
histogram_quantile(0.95, sum by (le) (rate(auth_me_get_latency_ms_bucket[5m])))

# 503s from the database being unavailable, across all endpoints
sum(rate({__name__=~".+_errors_total", http_status_code="503"}[5m]))

# Frontend error reports arriving
rate(client_errors_post_total[5m])
```

Metrics are exported every 60 seconds, so allow a minute or two after
traffic before they show up.

## Traces

One trace per request, with a span per SQL query. Search Tempo by
service name `hub-platform`. Useful for:

- Slow first requests: the trace shows whether time went to the app or
  to the first database connect (Neon resuming).
- `5xx` responses: the failing span carries the exception.

## Alerts

One alert today, in the Grafana Cloud stack:

- **Registration Error Rate > 10%** (dev): registration errors over 10%
  of requests for 5 minutes. Its contact point notifies the on-call
  person, who can run the on-call diagnostic
  (`custom-agent/on-call-diagnostic/README.md`).

Worth adding: a 5xx-rate alert across all endpoints, a p95 latency
alert on `auth_me_get`, and a rate alert on `client_errors_post_total`.

## Logs

CloudWatch log groups, 14-day retention (`infra/hub/lambda.tf`,
`infra/hub/bootstrap.tf`):

- `/aws/lambda/hub-<env>-backend` (`hub-dev`, `hub-prod`) for the
  API: request errors, origin
  verification rejections (`app.security` logger,
  `origin_verify_rejected ...`), frontend error reports
  (`app.client_errors` logger, `client_error {...json...}`).
- `/aws/lambda/hub-<env>-bootstrap`: migration and seed output per
  deploy.

CloudWatch Logs Insights, frontend errors in the last hour:

```
fields @timestamp, @message
| filter @message like /client_error/
| parse @message "client_error *" as report
| sort @timestamp desc
| limit 50
```

## Frontend errors in Grafana

Frontend error reports, database outages and origin-verification
rejections are exported to Grafana Cloud as OTLP log records (stored in
Loki), from the loggers listed in `EXPORTED_LOGGERS`
(`backend/observability/__init__.py`): `app.client_errors`, `app.db`,
`app.security`. Same OTLP endpoint and credentials as traces and
metrics, so nothing extra to configure; wherever `OTEL_ENABLED` is on
(the dev and prod Lambdas) they're exported. They still go to
CloudWatch too.

(Chosen 2026-10-03 over a CloudWatch data source in Grafana, which needs
an IAM role and UI setup, and over Grafana Faro in the browser, which
needs a new dependency and duplicates `/client-errors`.)

Grafana Explore, Loki data source:

```
# Every frontend error report, newest first
{service_name="hub-platform"} |= "client_error"

# Only one environment, one kind
{service_name="hub-platform", deployment_environment="prod"} |= "client_error" | client_error_kind="http"

# Database outages (503s) and rejected direct API calls
{service_name="hub-platform"} |~ "database_unavailable|origin_verify_rejected"
```

Each `client_error` line carries the report as JSON (`| json` parses
it), plus the attributes `client_error.kind` and, for failed API calls,
`client_error.status`. Records are exported synchronously as they're
logged (Lambda freezes between invocations), with a 2-second timeout and
a 60-second back-off after a failed export, like spans.

Checked locally against the repo's collector and Loki
(`backend/observability/docker-compose.yml`): a report sent to
`/client-errors` appears in Loki with `service_name=hub-platform`,
`client_error_kind`, `severity_text=WARN`.

## Local

The optional local stack (`backend/observability/docker-compose.yml`:
collector, Prometheus, Tempo, Loki, Grafana) is described in
`backend/observability/README.md`. Start the backend with
`OTEL_ENABLED=true` to send to it. Never point local traffic at Grafana
Cloud.

# Health checks

What to check, how, and what a healthy answer looks like.

## API liveness: GET /health

```
curl -s https://hub.dnls.dev/api/health       # prod
curl -s https://hub-dev.dnls.dev/api/health   # dev
curl -s http://localhost:8000/health          # local (no /api prefix)
```

Healthy: `200 {"status":"ok"}`.

It proves CloudFront, API Gateway and the Lambda are up and the app
imported cleanly (which means the JWT and origin-verify secrets loaded
from SSM: a Lambda that can't load them refuses to start). It does
**not** touch the database, on purpose: the CI and promote smoke tests
call it right after a deploy, and a probe that woke Neon or failed while
Neon was waking would make deploys flaky without telling you anything
the bootstrap step hadn't already.

Called directly against the `execute-api` URL instead of the site, it
returns `403`: origin verification only lets CloudFront through. That's
correct, not an outage.

## Database connectivity

There's no endpoint that reports database health. To check it:

- **Through the app**: sign in on the site, or call any authenticated
  route. `GET /api/auth/me` with a valid session returning `200` means
  the Lambda reached Postgres. A `503` with
  `"The database is temporarily unavailable..."` means it couldn't (see
  below).
- **The bootstrap**: invoking the bootstrap Lambda connects with the
  direct (non-pooled) URL and runs the migrations, a no-op at head.
  A success response proves the database is reachable and the schema
  is current:

  ```
  cd infra/hub && tofu workspace select dev
  aws lambda invoke --function-name "$(tofu output -raw bootstrap_function_name)" \
    --cli-binary-format raw-in-base64-out /tmp/bootstrap.json && cat /tmp/bootstrap.json
  ```

- **Neon console**: the project's branch shows whether the compute is
  active or suspended, and recent connection errors.
- **Locally**: `docker compose ps` (the `postgres` service has a
  `pg_isready` healthcheck), or `psql postgresql://postgres:postgres@localhost:5432/hub_dev`.

How the app responds when the database is down: every route that needs
it answers `503` with a `Retry-After` header instead of an unhandled
`500` (`app/main.py`, the `OperationalError` handler). The web app
treats that as "try again", never as "signed out".

## Lambda cold starts

A request that lands on a new Lambda container pays for:

1. Starting the container and importing the app (FastAPI, SQLAlchemy,
   OpenTelemetry, boto3). Typically one to a few seconds at 512 MB.
2. Fetching the JWT secret and the origin-verify secret from SSM, at
   import (two SSM calls).
3. On the first request that needs it, fetching the database URL from
   SSM and opening the first Postgres connection, which is lazy: the
   app does no database work at import.

Later requests on that container skip all of it. Warm containers keep
their pool of database connections; `pool_pre_ping` tests each one on
checkout and replaces it if Neon's pooler closed it while idle.

Cold starts stack with Neon's own: Neon suspends the compute after
about five minutes idle, and the first query after that waits for it to
resume (usually well under a second, occasionally a few seconds). The
first request after a quiet period can therefore take several seconds.
That's expected; see `ops/TROUBLESHOOTING.md` for what the app does
about it and for options to reduce it.

Signs a cold start is actually failing rather than slow:

- `502`/`503` from API Gateway with no app log line: the container
  didn't start. Check the Lambda's CloudWatch logs for an import-time
  `RuntimeError` (missing SSM parameter, default JWT secret).
- API Gateway's 30-second integration timeout reached: something hung
  (an SSM call or a database connect). Check CloudWatch for the
  request's log lines and the trace in Grafana.

## Local stack

`make docker-up` waits until `http://localhost:8000/health` answers. The
Compose services start in order (`postgres` healthy, then `bootstrap`
and `init_local` complete, then `app`), so a healthy `/health` locally
also means the migrations ran. `docker compose ps -a` shows each one-shot
service's exit code; a non-zero `bootstrap` or `init_local` means look at
`docker compose logs bootstrap init_local`.

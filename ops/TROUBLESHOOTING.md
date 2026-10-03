# Troubleshooting

Symptoms, causes, and what to check, most common first. Health checks
and where the logs are: `ops/HEALTH_CHECKS.md` and `ops/MONITORING.md`.

## Sent to the login page when the backend is slow or down (fixed)

**Symptom (before 2026-10-02):** a signed-in user opening the site after
a quiet period, or during a backend hiccup, landed on the login page as
if signed out. Logging in again worked.

**Root cause.** On load, the web app asks `GET /auth/me` whether the
httpOnly session cookie is valid (it can't read the cookie itself).
`frontend/src/auth.tsx` treated *any* failure of that call as "no
session":

```ts
authApi.getCurrentUser()
  .then(...authenticated)
  .catch(() => setStatus('unauthenticated'))   // every error, not just 401
```

So a network error, a `5xx`, or a timeout looked exactly like a 401.
Nothing was wrong with the session; the cookie was still there and
still valid.

Two things made it worse:

1. **The backend returned an unhandled `500` when the database was
   unreachable.** An unhandled exception is answered by Starlette's
   outermost error middleware, outside `CORSMiddleware`, so the `500`
   had no CORS headers. Locally the frontend (:5173) and API (:8000) are
   different origins, so the browser reported it as a network error
   rather than a `500`, which hid the real cause while debugging.
2. **Neon suspends after about five minutes idle.** The first query
   afterwards waits for the compute to resume, and a Lambda cold start
   can stack on top (`ops/HEALTH_CHECKS.md`). That's normally just slow,
   but it's exactly when a transient failure is most likely.

The 401 handler for requests *after* load (`setUnauthorizedHandler` in
`frontend/src/services/api/http.ts`) was never the problem: it fires
only on a real `401`.

**Fix.**

- `frontend/src/auth.tsx`: only a `401` means signed out. Any other
  failure is retried once after 500 ms (`SESSION_RETRY_DELAY_MS`). If the
  retry also fails without a `401`, the status becomes `unreachable` and
  `App.tsx` shows **"Can't reach the server"** with a **Try again**
  button, not the login page. The session cookie is never touched.
- `backend/app/main.py`: a SQLAlchemy `OperationalError` (database
  unreachable) is answered with `503`, `Retry-After: 2` and a generic
  message, from inside the CORS layer, so it keeps its CORS headers. The
  underlying error is logged on the `app.db` logger
  (`database_unavailable method=... path=... error=<exception type>`),
  not returned.
- Failed calls (no response or `5xx`) are also reported to
  `POST /client-errors`, so they show up in the logs.

**Tests.** `src/auth.test.tsx` ("session check when the backend is
unavailable"), `src/App.test.tsx` ("Backend unreachable on load"),
`backend/tests/test_database_unavailable.py`, and in
`frontend/tests/integration.spec.ts`: a retried session check, an
unreachable backend, and (with `E2E_DOCKER=1`) Postgres stopped and
Postgres paused, against the Docker Compose stack.

**If it happens again:**

1. Open the browser dev tools Network tab and reload. Look at
   `GET /api/auth/me`:
   - `401`: genuinely signed out (cookie expired after 60 minutes, or
     the JWT secret was rotated). Expected.
   - `503`: the database was unreachable; the app should be on the
     "Can't reach the server" screen, not login. Check Neon.
   - failed / no response: CloudFront, API Gateway or the Lambda. Check
     `/api/health`.
2. If the login page appeared on anything but a `401`, that's a
   regression in `auth.tsx`; the unit tests above should have caught it.

## First request after idle is slow (Neon cold start)

**Symptom:** the first page load after a few minutes of no traffic takes
several seconds; later ones are fast.

**Cause:** Neon suspends the compute after about five minutes idle and
the first query waits for it to resume, sometimes on top of a Lambda
cold start. Expected behaviour for a scale-to-zero database.

What's already in place:

- `pool_pre_ping` (`backend/app/db/session.py`): a pooled connection
  that Neon's pooler closed while idle is replaced on checkout instead
  of failing the request.
- The frontend's session-check retry and the backend's `503` handling
  (above), so a slow or failed first request doesn't sign anyone out.

Options if it needs to be faster, with their costs:

1. **Raise Neon's suspend timeout** (or disable scale-to-zero) for the
   prod branch, in the Neon console. Simplest; costs compute hours,
   and on the free plan the timeout may not be adjustable.
2. **Keep-warm ping**: a scheduled job (EventBridge rule invoking the
   Lambda, or a GitHub Actions cron) that runs a query every four
   minutes. Keeps both Neon and one Lambda container warm, and keeps the
   Neon compute running around the clock, which is the same cost as
   option 1 with more moving parts.
3. **Provisioned concurrency** on the API Lambda removes Lambda cold
   starts but not Neon's, and costs money per hour.

How to tell which one you're seeing: the request's trace in Grafana.
Time before the first span is Lambda start-up; a long first `connect`
or query span is Neon resuming.

## Local reproduction of an outage

With the Compose stack up (`make docker-up`) and the frontend on :5173:

```
docker compose stop postgres     # API answers 503; app shows "Can't reach the server"
docker compose start postgres    # then click "Try again"
docker compose pause postgres    # simulated Neon sleep: requests hang
docker compose unpause postgres  # ...and complete when it "wakes"
```

`make test-e2e-docker` runs these scenarios as tests.

## Bootstrap fails on deploy

**Symptom:** the "Bootstrap schema" step of `ci.yml` or `promote.yml`
fails; `/tmp/bootstrap.json` has an `errorMessage`.

The deploy stops there, before the full apply: the API Lambda is still
on the old image, the schema is unchanged (Postgres rolls a failed
migration back), and the site keeps working as before. Only the
bootstrap function has the new image. Fix the cause and re-run the
deploy.

Common causes:

- **`Database has some of the app's tables but not all ... Refusing to
  guess`**: a database with a partial schema and no `alembic_version`.
  Never produced by this app; someone created or dropped tables by hand.
  Fix the schema by hand, then
  `uv run alembic stamp <revision>` against it.
- **`Can't add length limits: existing data is already longer`**
  (migration `0002`): some rows already exceed the new text limits. The
  message lists which column and how many rows. Shorten those values by
  hand (they're user data, so decide with the owner), or raise the
  limit in a new migration, then deploy again. To see them on Postgres:
  `SELECT id, length(description) FROM projects WHERE length(description) > 5000;`
  (and likewise for the other columns).
- **A migration error** (`ProgrammingError`, `DuplicateTable`, ...): the
  migration doesn't match the database. On Postgres the whole run is one
  transaction, so nothing was applied. Fix the migration, push, redeploy.
- **Can't connect**: wrong or missing `DB_URL_PARAM_NAME` parameter, or
  Neon unavailable. The bootstrap uses the direct (non-pooled) URL.
- **Timeout**: the bootstrap Lambda has 60 seconds. A long data
  migration on a large table needs a different approach (batched, or
  run by hand).

Locally, `docker compose logs bootstrap init_local` shows the same
output.

## init_local stops at migration 0002 (local database)

**Symptom:** `python -m app.db.init_local` (or Compose's `init_local`)
fails with `Can't add length limits: existing data is already longer`.

**Cause:** the local database holds values longer than the new text
limits. Usually old E2E test data: before the limits, the Playwright
suite deliberately stored 10,000-character names and 100,000-character
notes, for throwaway `e2e-*@example.com` users.

**Fix**, either:

- Reset the local SQLite database: `rm backend/hub.db`, then
  `SEED_DEMO_DATA=true uv run python -m app.db.init_local`. (For
  Compose: `docker compose down -v`.) Loses all local data.
- Or delete just the over-long rows, after checking they're test data.
  From `backend/`, for SQLite:

  ```
  sqlite3 hub.db "
    CREATE TEMP TABLE too_long AS SELECT id FROM projects
      WHERE length(name) > 256 OR length(pitch) > 2000
         OR length(description) > 5000 OR length(next_action) > 1000;
    DELETE FROM notes WHERE length(body) > 10000
      OR project_id IN (SELECT id FROM too_long);
    DELETE FROM projects WHERE id IN (SELECT id FROM too_long);"
  ```

  (Notes are deleted explicitly because the `sqlite3` shell doesn't
  enforce foreign keys, so it wouldn't cascade.)

## Migration drift test fails

`tests/test_migrations.py::test_migrations_match_the_orm_models` fails:
`app/db/orm.py` changed without a migration. From `backend/`:

```
uv run alembic revision --autogenerate -m "describe the change"
```

Read the generated file in `alembic/versions/` before committing:
autogenerate can't tell a rename from a drop plus an add, and doesn't
write data migrations.

## Getting 429 Too Many Requests

From `/auth/login`, `/auth/register` or `/client-errors`: the per-IP
limit (`security/RATE_LIMITING.md`). Wait for `Retry-After` seconds.
Behind Cloudflare, the limit is per user only once `TRUSTED_PROXY_IPS`
holds Cloudflare's ranges; until then it's per Cloudflare edge, so other
users' attempts can count against you (`ops/DEPLOYMENT.md`, "Trusted
proxies").

From every route at once: the API Gateway stage throttle (50 rps,
burst 100).

## Getting 403

- `{"detail": "Forbidden"}` on every route: the request didn't come
  through CloudFront (origin verification). Use the site URL, not the
  `execute-api` URL.
- A message about a limit (`Project limit reached`, `Sign-ups are
  closed`): a usage cap (`backend/README.md`, "Usage caps").

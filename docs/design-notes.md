# Design notes

Build decisions worth knowing that aren't obvious from the code. Not a task list, see `tech-debt.md` for that.

## Storage: SQLite locally, Postgres deployed

The backend runs on SQLite via SQLAlchemy for local dev and unit tests, and on Neon Postgres 17 when deployed (Postgres 17 in Docker Compose for prod parity and the integration tests). The schema is deliberately kept portable, so the same models and migrations run on both. Specific tradeoffs made for that portability:

1. No SQLite driver package needed (stdlib); Postgres uses `psycopg[binary]`.
2. UUIDs as `String(36)`, not Postgres's native UUID type.
3. Tags and links stored as generic JSON, not Postgres JSONB. Costs some Postgres-side JSON query and index efficiency later.
4. Free text stored as `Text`, not `VARCHAR(n)`, to avoid a dev-vs-prod silent-truncation trap. Length limits are CHECK constraints instead (`length(col) <= n`, which counts characters on both), mirroring the API's own validation; the limits are defined once, in `app/models/`.
5. Status enum via SQLAlchemy `Enum(values_callable=...)`: this becomes a native ENUM on Postgres, and VARCHAR plus a check constraint on SQLite.
6. Timezone-aware timestamps: `DateTime(timezone=True)` is correct on both, but SQLite strips tzinfo on read. A `_utc()` helper in `store.py` reattaches UTC when missing. This masks the SQLite gap at the store layer rather than fixing it at the database; reading timestamps straight off the SQLite file, bypassing the store, would give naive datetimes.
7. Foreign key enforcement is turned on for SQLite (`PRAGMA foreign_keys=ON` per connection) so dev behavior matches Postgres, which enforces FKs by default. Except during migrations: SQLite applies most schema changes by rebuilding the table, and with FKs on, dropping the old `projects` table would cascade-delete every note. `app/db/migrations.py` runs migrations with FKs off and in one real transaction (the `sqlite3` driver otherwise commits DDL early).
8. Counts in JSON arrays (tags, links) are capped with `json_array_length()`, which both databases have; per-element lengths can't be checked portably in a CHECK constraint, so those are API-only.

## Migrations before code

Schema changes are Alembic migrations, applied on every deploy by the bootstrap Lambda before the API Lambda switches to new code. So for a short window the old code runs against the new schema: migrations must stay additive (new tables, nullable columns, constraints the old code can't violate), and renames or drops come a release after the code stops using them. A migration that adds a limit refuses to run over existing data that breaks it instead of truncating anything. See `ops/DEPLOYMENT.md`.

## Auth

Auth is roll-your-own (argon2 password hashing, JWTs) rather than a managed provider. The same JWT works two ways: the web app gets it in an httpOnly, SameSite=Strict cookie (JavaScript never sees it, so XSS can't steal it), and API clients send it as a bearer header. Tokens are stateless, so there's no server-side session store.

Signed-out is decided only by a 401. On load the web app asks `/auth/me`; any other failure (network, 5xx, a database outage answered with 503) is retried once, then shown as "Can't reach the server", never as the login page.

`auth_identities` is a separate table from `users`, keyed by provider, so additional sign-in methods could attach to an existing account later without reshaping the `users` table. Only the `password` provider is wired today.

## Frontend api-layer seam

All frontend data access goes through `frontend/src/services/api/`; components never call `fetch` directly. This is the single seam between the UI and the backend, so a different consumer of the same backend would only need to implement this layer, not touch any component.

## Errors and logs go through the backend

The browser reports errors to the backend (`POST /client-errors`), which logs them; the backend exports those logs to Grafana with the same OpenTelemetry pipeline as traces and metrics. No browser SDK, no third-party script, and one place to rate-limit and scrub what's recorded.

## No inline scripts

The deployed site sends a strict Content-Security-Policy (`script-src 'self'`). Anything that must run before React, like the theme script that avoids a flash of the wrong theme, is a file under `frontend/public/`, not inline.

## Write convention: pessimistic

Every write in the store (create, update, delete) waits for the API response before local state changes. Nothing is applied optimistically and then rolled back on failure. Reasons: state is always backend-confirmed, so there is nothing to roll back; individual writes are cheap and form inputs already echo keystrokes immediately, so the UI stays responsive without optimistic updates.

## Testing conventions

- This repo runs Vitest without global test APIs (tests import `describe`/`it`/etc. from `vitest` explicitly), so React Testing Library's automatic between-test cleanup does not fire on its own. It is wired manually via `afterEach(() => cleanup())` in `frontend/src/test-setup.ts`. Do not remove it.
- base-ui's `Dialog` keeps its content in the DOM (hidden) while closed rather than unmounting it. A broad query, such as `getByRole('button', { name: /capture/i })`, on any page with the quick-capture dialog mounted can match both the visible trigger and the hidden dialog's own content. Scope such queries to a landmark, such as the header, to disambiguate.

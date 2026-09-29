# Design notes

Build decisions worth knowing that aren't obvious from the code. Not a task list, see `tech-debt.md` for that.

## Storage: SQLite now, Postgres later

The backend runs on SQLite via SQLAlchemy for local dev. The schema is deliberately kept portable so a move to Postgres is a `DATABASE_URL` change plus adding a driver, not a rewrite. Specific tradeoffs made for that portability:

1. No SQLite driver package needed (stdlib). Postgres will need `uv add psycopg[binary]`.
2. UUIDs as `String(36)`, not Postgres's native UUID type.
3. Tags and links stored as generic JSON, not Postgres JSONB. Costs some Postgres-side JSON query and index efficiency later.
4. Free text stored as unbounded `Text`, not `VARCHAR(n)`, to avoid a dev-vs-prod silent-truncation trap.
5. Status enum via SQLAlchemy `Enum(values_callable=...)`: this becomes a native ENUM on Postgres, and VARCHAR plus a check constraint on SQLite.
6. Timezone-aware timestamps: `DateTime(timezone=True)` is correct on both, but SQLite strips tzinfo on read. A `_utc()` helper in `store.py` reattaches UTC when missing. This masks the SQLite gap at the store layer rather than fixing it at the database; reading timestamps straight off the SQLite file, bypassing the store, would give naive datetimes.
7. Foreign key enforcement is turned on for SQLite (`PRAGMA foreign_keys=ON` per connection) so dev behavior matches Postgres, which enforces FKs by default.

## Auth

Auth is roll-your-own (argon2 password hashing, JWT bearer tokens) rather than a managed provider or cookie/session auth. Token-based auth means the same API can serve a browser client and any other client type identically, without a session-cookie dependency.

`auth_identities` is a separate table from `users`, keyed by provider, so additional sign-in methods could attach to an existing account later without reshaping the `users` table. Only the `password` provider is wired today.

## Frontend api-layer seam

All frontend data access goes through `frontend/src/services/api/`; components never call `fetch` directly. This is the single seam between the UI and the backend, so a different consumer of the same backend would only need to implement this layer, not touch any component.

## Write convention: pessimistic

Every write in the store (create, update, delete) waits for the API response before local state changes. Nothing is applied optimistically and then rolled back on failure. Reasons: state is always backend-confirmed, so there is nothing to roll back; individual writes are cheap and form inputs already echo keystrokes immediately, so the UI stays responsive without optimistic updates.

## Testing conventions

- This repo runs Vitest without global test APIs (tests import `describe`/`it`/etc. from `vitest` explicitly), so React Testing Library's automatic between-test cleanup does not fire on its own. It is wired manually via `afterEach(() => cleanup())` in `frontend/src/test-setup.ts`. Do not remove it.
- base-ui's `Dialog` keeps its content in the DOM (hidden) while closed rather than unmounting it. A broad query, such as `getByRole('button', { name: /capture/i })`, on any page with the quick-capture dialog mounted can match both the visible trigger and the hidden dialog's own content. Scope such queries to a landmark, such as the header, to disambiguate.

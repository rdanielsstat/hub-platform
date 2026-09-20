# Tech debt

Known issues deferred for later, from the read-only code review and subsequent work. None are bugs or blockers; they're consistency, robustness, and roadmap items to address when convenient (ideally when already working in the relevant file, or as noted, alongside the backend).

## Security (before deploy / before first paid user)

- **Rate-limiting on signup/login** → open registration on a pay-per-use backend is an abuse surface. Not needed on localhost; add before the backend is publicly reachable.
- **Account / project caps per user** → a simple cap while costs are unguarded, to avoid a single actor running up usage. Decide alongside rate-limiting.
- **CORS origins are hardcoded to localhost** → `backend/app/main.py`'s `allow_origins` only lists `localhost:5173`/`127.0.0.1:5173`. Safe as a restrictive default, but the deployed frontend's origins (prod + staging) must be added there at deploy time or every request fails CORS.
- **Observability (Sentry) not wired up** → spec §2 calls for error tracking (Sentry, React + FastAPI) as part of v1. A frontend error boundary now catches render crashes with a graceful fallback (see `components/error-boundary.tsx`), but nothing reports errors anywhere yet, frontend or backend. Deliberately deferred to the deploy phase, not an oversight.

## Portability tradeoffs (for the eventual Postgres/Neon swap)

1. No SQLite driver package needed (stdlib). Postgres will need `uv add psycopg[binary]`.
2. UUIDs as String(36), not Postgres native UUID.
3. Tags and links as generic JSON, not Postgres JSONB (costs some Postgres-side JSON query/index efficiency later).
4. Free text as unbounded Text, not VARCHAR(n), to avoid a dev-vs-prod silent-truncation trap.
5. Status enum via SQLAlchemy Enum(values_callable=...) — native ENUM on Postgres, VARCHAR+check on SQLite.
6. Timezone-aware timestamps: DateTime(timezone=True) correct on both, but SQLite strips tzinfo on read. A _utc() helper in store.py reattaches UTC when missing. Masks the SQLite gap at the store layer rather than fixing it at the DB — reading timestamps straight off the SQLite file bypassing the store would give naive datetimes.
7. FK enforcement turned on for SQLite (PRAGMA foreign_keys=ON per connection) so dev matches Postgres.

## Migrations

- **No Alembic yet** → tables are created on startup via `create_all()` (creates missing tables, can't alter existing ones). Fine while the schema is still moving pre-launch. Once it stabilizes, convert to real Alembic migrations so schema changes are tracked and reversible.

## Spec / roadmap (not debt, remaining build work)

- **Attachments** — spec §3/§4.3 define an attachments table and project-detail UI; none exists yet. Deferred; not critical for v1. Needs an upload-mechanism decision (direct-to-S3 presigned vs proxied) before building.
- **PWA installability** — spec calls for installable-as-PWA; no manifest or service worker yet.
- **Deploy** — Vercel (frontend) + Neon Postgres (backend). Triggers the Postgres swap above and the security items above.

## Open questions

- **Logout-on-any-failure may be too aggressive** → the app currently routes to login whenever the backend becomes unreachable, not only on a real 401. A brief network blip or a scale-to-zero cold-start could fully log the user out mid-session rather than just showing a transient error. Revisit whether the onUnauthorized/redirect path should fire only on an actual 401, with other failures handled as retryable errors that keep the session. Surfaced during the error-handling work; not yet root-caused (also entangled with an environment quirk seen in the automated browser tab).

## Notes

- A minor deviation from the em-dash pass: the `'—'` "no date" placeholder was originally replaced with an empty string rather than punctuation. Both branches that produced it have since been deleted outright (the consistency cleanup removed `formatDate`'s null-`iso` case and the `due` fallback in `project-detail.tsx`); today a project with no target date just shows nothing there. The underlying product question is still open: decide whether it should show something like "None" instead of nothing.

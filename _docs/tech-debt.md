# Tech debt

Deferred work: items that can't be done until deploy, or that are deliberately deferred future work. Not a bug list; nothing here is a current defect.

## Security (before deploy / before first paid user)

- **Rate-limiting on signup/login** → open registration on a pay-per-use backend is an abuse surface. Not needed on localhost; add before the backend is publicly reachable.
- **Account / project caps per user** → a simple cap while costs are unguarded, to avoid a single actor running up usage. Decide alongside rate-limiting.
- **CORS origins are hardcoded to localhost** → `backend/app/main.py`'s `allow_origins` only lists `localhost:5173`/`127.0.0.1:5173`. Safe as a restrictive default, but the deployed frontend's origins (prod + staging) must be added there at deploy time or every request fails CORS.
- **Observability (Sentry) not wired up** → a frontend error boundary now catches render crashes with a graceful fallback (see `components/error-boundary.tsx`), but nothing reports errors anywhere yet, frontend or backend. Deliberately deferred to the deploy phase, not an oversight.

## Migrations

- **No Alembic yet** → tables are created on startup via `create_all()` (creates missing tables, can't alter existing ones). Fine while the schema is still moving pre-launch. Once it stabilizes, convert to real Alembic migrations so schema changes are tracked and reversible.

## Deferred features

- **Attachments** — not built. Deferred; not critical for v1. Needs an upload-mechanism decision (direct-to-S3 presigned vs proxied) before building.
- **PWA installability** — no manifest or service worker yet.
- **Deploy** — Vercel (frontend) + Neon Postgres (backend). Triggers a storage swap and the security items above.

## Open questions

- **Logout-on-any-failure may be too aggressive** → the app currently routes to login whenever the backend becomes unreachable, not only on a real 401. A brief network blip or a scale-to-zero cold-start could fully log the user out mid-session rather than just showing a transient error. Revisit whether the onUnauthorized/redirect path should fire only on an actual 401, with other failures handled as retryable errors that keep the session. Surfaced during the error-handling work; not yet root-caused (also entangled with an environment quirk seen in the automated browser tab).

# Hub frontend

Vite 6 + React 19 SPA. Stack, conventions and the rules for agents are in
the repo root's `AGENTS.md`; the product spec is `product-spec.md` at the repo root.

## Setup

Node 22 and pnpm 12.3 (pinned in `package.json`).

```
pnpm install
cp .env.example .env   # points the app at a local backend on :8000
pnpm dev               # http://localhost:5173
```

All data access goes through `src/services/api/`; components never call
`fetch` directly. `VITE_API_BASE_URL` (see `.env.example`) sets where
requests go: `http://localhost:8000` locally, unset (same-origin `/api`)
in every deployed build.

## Build and deploy

`pnpm build` runs `tsc -b` then `vite build` into `dist/`. CI builds with
`VITE_API_BASE_URL=/api`, so one artifact works for every environment
(the API is same-origin behind CloudFront), syncs `dist/` to the
environment's S3 bucket and invalidates CloudFront. Dev gets it on every
push to `main`; `promote.yml` rebuilds it from the current `main` for
prod (`ops/DEPLOYMENT.md`). Static files in `public/` (`favicon.svg`,
`theme-init.js`) are copied as they are.

## Checks

All must pass before a change is done (`make check` from the repo root
runs them, plus the backend unit tests):

```
pnpm test           # Vitest unit tests
pnpm lint           # ESLint, 0 errors / 0 warnings
pnpm build          # tsc -b && vite build
pnpm format:check   # Prettier
```

## Tests

### Unit (Vitest)

`pnpm test`. React Testing Library on jsdom, colocated with the code
(`src/**/*.test.ts(x)`). No backend or browser needed; `fetch` is mocked
per test. `test.globals` is off, so tests import from `vitest`
explicitly, and `src/test-setup.ts` wires RTL's cleanup by hand.

### End to end (Playwright)

In `tests/`, configured by `playwright.config.ts`. Playwright starts the
Vite dev server itself (or reuses one already on :5173), pointed at
`E2E_API_URL` (default `http://localhost:8000`). It never starts the
backend: run one first. Install the browser once with
`pnpm exec playwright install chromium`.

| Project          | Specs                                             | Needs                                                                                                       | Run                                                                                                      |
| ---------------- | ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `chromium`       | `app.spec.ts` (browser), `api.spec.ts` (API only) | Any backend on :8000: `uv run uvicorn app.main:app` in `backend/` (SQLite), or the Compose stack (Postgres) | `make test-e2e`, or `pnpm exec playwright test --project=chromium`                                       |
| `docker-compose` | `integration.spec.ts`                             | The Compose stack (`make docker-up`)                                                                        | `make test-e2e-docker`, or `E2E_DOCKER=1 pnpm exec playwright test --project=docker-compose --workers=1` |

`integration.spec.ts` covers a full journey on Postgres, browser error
reporting, and how the app behaves when the backend or database is
unavailable. Its "database outage" tests stop, start and pause the
Compose `postgres` service through the docker CLI, so they only run with
`E2E_DOCKER=1`, and the project must run alone with one worker, or other
tests would lose their database mid-run.

Every test registers its own user, so tests are isolated and can run in
parallel. Rate limits are off on a local or Compose backend, so the
suites can sign up and log in freely. `E2E_JWT_SECRET` must match the
backend's `HUB_JWT_SECRET` if that's set (the token-forging tests skip
themselves otherwise).

CI (`.github/workflows/ci.yml`, `e2e` job) runs both projects against the
Compose stack on every PR and push, and uploads the HTML report when
they fail.

## Theme

Light and dark, following the system setting until the user picks one.
`public/theme-init.js` runs before first paint (a blocking
`<script src>` in `index.html`, not inline, for the CSP): it reads
`localStorage['hub.theme']` and the `prefers-color-scheme` media query
and sets the `dark` class on `<html>`. `src/lib/theme.ts` stores the
choice (`THEME_STORAGE_KEY`, kept in sync with the literal in
`theme-init.js`) and corrects the `theme-color` meta tag once React has
mounted. The theme is the only thing the app keeps in `localStorage`.

## Form validation

The forms check what's required before enabling submit: a project name
(quick capture), email and password on login, email and an 8-character
password on sign-up, non-blank notes, tags and link URLs. Tags are
trimmed and lowercased; link URLs get `https://` added when there's no
scheme. Everything else is validated by the API: over-long fields, too
many tags or links, bad scores or URLs come back as `422`, and the
backend's message (for example "String should have at most 256
characters") is shown as a toast (`src/lib/errors.ts`).

Every text field also has a `maxLength` matching the API's limit, from
`src/lib/limits.ts` (email 254, password 256, display name 100, project
name 256, pitch 2000, description 5000, next action 1000, note 10000, tag
64, link URL 2048, link label 200), so the browser stops typing and
pasting at the limit instead of the user finding out on save.
`backend/tests/test_frontend_limits.py` fails if `limits.ts` and the API
disagree. Two fields can still reach a 422: the quick-capture tags field
takes comma-separated tags, so it's capped as a whole (room for 50
full-length tags) rather than per tag; and a link URL typed without a
scheme gets `https://` added, so one at the full 2048 ends up 8 over.
`maxLength` counts UTF-16 units, so emoji-heavy text stops slightly
before the API's character limit, never after.

## Error reporting

`src/lib/error-reporting.ts`, installed from `main.tsx`, sends uncaught
errors, unhandled promise rejections, failed API calls (no response, or
a 5xx) and React render crashes (`components/error-boundary.tsx`) to the
backend's `POST /client-errors`, which logs them; deployed, the backend
exports those logs to Grafana Cloud (Loki), where they can be queried
with `{service_name="hub-platform"} |= "client_error"`
(`ops/MONITORING.md`). At most 20 reports per page load, each distinct
one once, fire-and-forget, with no query strings in URLs. Nothing is
sent from unit tests: reporting stays off until `installErrorReporting()`
runs. See `backend/README.md` ("Frontend error reports").

## Content-Security-Policy

Deployed, CloudFront sends a strict CSP (`infra/hub/frontend.tf`):
scripts only from the site itself, with no inline `<script>`, plus the
Cloudflare Web Analytics beacon that Cloudflare's proxy injects; styles
and fonts from the site and Google Fonts; API calls same-origin. So:

- Don't add inline scripts to `index.html`. Code that has to run before
  React (like the theme, to avoid a flash) goes in a file under
  `public/` and loads with `<script src>`; see `public/theme-init.js`.
- Loading anything from a new origin (a CDN, an analytics script, an
  image host) needs that origin added to the CSP first, or the browser
  blocks it. The dev server sends no CSP, so this only fails deployed.

## Session check

On load, `src/auth.tsx` asks `GET /auth/me` whether the session cookie is
valid. Only a `401` means signed out. Any other failure (no response, a
5xx) is retried once after 500 ms; if that fails too, the app shows a
"Can't reach the server" screen with a retry button instead of the login
page, and the session is kept. See `ops/TROUBLESHOOTING.md`.

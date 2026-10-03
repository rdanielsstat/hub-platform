# Hub frontend

Vite 6 + React 19 SPA. Stack, conventions and the rules for agents are in
the repo root's `AGENTS.md`; the product spec is `docs/specs.md`.

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

## Error reporting

`src/lib/error-reporting.ts`, installed from `main.tsx`, sends uncaught
errors, unhandled promise rejections, failed API calls (no response, or
a 5xx) and React render crashes (`components/error-boundary.tsx`) to the
backend's `POST /client-errors`, which logs them. At most 20 reports per
page load, each distinct one once, fire-and-forget. Nothing is sent from
unit tests: reporting stays off until `installErrorReporting()` runs. See
`backend/README.md` ("Frontend error reports").

## Content-Security-Policy

Deployed, CloudFront sends a strict CSP (`infra/hub/frontend.tf`):
scripts only from the site itself, with no inline `<script>`; styles and
fonts from the site and Google Fonts; API calls same-origin. So:

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

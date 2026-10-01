---
name: e2e-testing
description: Run Playwright end-to-end tests, validate test fixtures, report results and edge cases
---

# E2E Testing

Run Hub-Platform's Playwright end-to-end suite against the real local backend and frontend, then report the results. Nothing is mocked except a few deliberately failed requests in error-state tests.

## When to run

- Before submitting a feature for QA review
- After QA reports issues (re-run to verify fixes)
- Before tagging a release (via `release` skill or on demand)
- On demand to validate any critical flow

## The suite

All tests live in `frontend/tests/` (187 tests as of October 2026; the count grows as tests are added):

```
frontend/tests/
  app.spec.ts   Browser tests: signup, login, logout and session handling;
                dashboard (loading, error, empty and no-matches states, search,
                badges); create, filter, sort, edit and delete projects; notes;
                two tabs editing the same project; rapid sequences; phone and
                tablet viewports
  api.spec.ts   API tests with Playwright's request fixture (no browser): every
                endpoint, with success cases, 401/404/409/422 errors, field
                validation, response shapes, cascading deletes, and isolation
                between users
  helpers.ts    Shared setup: register users and create projects or notes
                through the API, sign the browser in, wait for API calls,
                hold requests to test in-flight states, forge test tokens
```

How the tests stay independent:

- Every test registers its own user through the API, with a unique email (`crypto.randomUUID()`). Nothing depends on the demo account or on another test's data, so tests run in parallel and need no cleanup.
- Setup goes through the API; the browser only drives the flow under test.
- Error states use `page.route()` to make one specific backend call fail. Everything else hits the real backend.

`playwright.config.ts` runs Chromium only, with `baseURL` `http://localhost:5173`.

## Prerequisites

- Backend running on `http://localhost:8000`, from `backend/`:
  ```bash
  uv run uvicorn app.main:app --reload
  ```
- Database initialized once, from `backend/`:
  ```bash
  SEED_DEMO_DATA=true uv run python -m app.db.init_local
  ```
- `frontend/.env` copied from `frontend/.env.example`, so `VITE_API_BASE_URL=http://localhost:8000` (no `/api` locally)
- Frontend dev server running on `http://localhost:5173`, from `frontend/`:
  ```bash
  pnpm dev
  ```
- Frontend dependencies installed (`pnpm install` in `frontend/`, which includes `@playwright/test`)

To look around the app by hand, log in as the seeded demo account: `demo@hub.dev` / `demo1234`. The tests themselves never use it.

## Steps

### 1. Verify the environment

```bash
# Backend health check: should return {"status":"ok"}
curl http://localhost:8000/health

# Frontend dev server: should return 200
curl -o /dev/null -w '%{http_code}\n' http://localhost:5173/
```

If either fails, ask the human to start it.

### 2. Install the browser (first run only)

From `frontend/`:

```bash
pnpm exec playwright install chromium
```

### 3. Run the suite

From `frontend/`:

```bash
pnpm exec playwright test
```

Useful variations:

```bash
# One file
pnpm exec playwright test tests/api.spec.ts

# Tests whose name matches a pattern
pnpm exec playwright test -g "notes"

# Watch the browser
pnpm exec playwright test --headed

# Step through with the inspector
pnpm exec playwright test --debug

# Check for flaky tests
pnpm exec playwright test --repeat-each=3
```

Optional environment variables (read in `tests/helpers.ts`):

- `E2E_API_URL`: the backend the tests call directly (default `http://localhost:8000`)
- `E2E_JWT_SECRET`: the backend's JWT signing secret, used by the expired- and forged-token tests (default: the built-in dev secret). If it doesn't match the running server, those tests skip themselves.

### 4. Review the results

```bash
pnpm exec playwright show-report
```

The HTML report shows each test's result, timing, errors, and a trace for failures that were retried. For a failing test, also read `test-results/<test>/error-context.md`, which includes a snapshot of the page.

### 5. Report

```
E2E Test Results
================

Environment:
  Backend:  http://localhost:8000  ✓
  Frontend: http://localhost:5173  ✓

Results:
  Passed:  <N>
  Failed:  <N>
  Skipped: <N> (forged-token tests skip if E2E_JWT_SECRET doesn't match)
  Flaky:   <N>
  Time:    <Xs>

Failures:
  - <file>:<line> <test name>: <error message>

Status: [✓ PASS | ⚠ FLAKY | ✗ FAIL]
```

## Writing new tests

- Put browser flows in `app.spec.ts` and API-only checks in `api.spec.ts`, inside the matching `test.describe` block.
- Create users and data with the helpers (`registerViaApi`, `createProjectViaApi`, `addNoteViaApi`), never through shared fixtures or the demo account.
- Sign the browser in with `signInAs(page, user)`. Don't use it in a test that signs out: its init script puts the token back on the next navigation.
- Wait for the dashboard's data with `openDashboard(page)` and for API calls with `waitForApi(page, method, path)`, not fixed timeouts.
- Prefer the selectors the components already expose: element ids (`#signup-email`, `#qc-name`), `aria-label`s, roles and labels.
- After a client-side navigation, the URL changes before React swaps the page, so wait for an element on the new page before filling inputs.
- Use unique names (`uid()`) for anything a test creates.

## Troubleshooting

**Every test fails at the first API call:**
- Check the backend is running on port 8000 and `curl http://localhost:8000/health` works.
- Check `frontend/.env` exists; without it the frontend calls `/api`, which only exists behind CloudFront. Restart `pnpm dev` after creating it.

**Browser not found:**
```bash
pnpm exec playwright install chromium
```

**Forged-token tests are skipped:**
The server isn't using the dev JWT secret. Set `E2E_JWT_SECRET` to the server's secret, or accept the skips.

**Tests are flaky:**
- Replace any fixed waits with `waitForApi` or web-first assertions (`await expect(locator).toBeVisible()`).
- Use `holdRequests` to test in-flight states (disabled buttons, skeletons) instead of racing the server.

## Limitations

- Runs against local dev only, not the deployed dev or prod environments.
- Not run in CI yet.
- Chromium only.
- Test users accumulate in the local database (`backend/hub.db`); delete the file and re-run `init_local` to start fresh.

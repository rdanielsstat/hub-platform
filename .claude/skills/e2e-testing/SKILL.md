---
name: e2e-testing
description: Run Playwright end-to-end tests, validate test fixtures, report results and edge cases
---

# E2E Testing

Execute comprehensive end-to-end tests using Playwright. Validate user flows, critical paths, and edge cases against a running instance of the app.

## When to run

- Before submitting a feature for QA review
- After QA reports issues (re-run to verify fixes)
- Before tagging a release (via `release` skill or on demand)
- On demand to validate any critical flow

## Prerequisites

- Backend is running: `uv run uvicorn app.main:app --reload` from `backend/`
- Frontend dev server is running: `pnpm dev` from `frontend/`
- Backend has been initialized: `SEED_DEMO_DATA=true uv run python -m app.db.init_local` (done once)
- Playwright is installed: `pnpm install` from `frontend/` (includes Playwright)
- `VITE_API_BASE_URL` is set in `frontend/.env` to point to the backend (default: `http://localhost:8000/api`)

## Steps

### 1. Verify test environment

Confirm both servers are running and responding:

```bash
# Backend health check
curl http://localhost:8000/api/health

# Frontend dev server check
curl http://localhost:5173/
```

Both should return 2xx status. If not, start the servers first.

### 2. Install Playwright browsers (first run only)

Playwright needs the browser binaries. From `frontend/`:

```bash
pnpm exec playwright install
```

This downloads Chromium, Firefox, and WebKit. It's a one-time setup (or run again if browsers are missing).

### 3. Run the full test suite

From `frontend/`:

```bash
pnpm exec playwright test
```

This runs all `.spec.ts` files in the `tests/e2e/` directory (when created).

**Test scope should include:**

- **Authentication**: login, logout, token expiry, invalid credentials
- **Project CRUD**: create, read, update, delete projects
- **Interview flow**: capture interview ideas, organize, triage
- **Search and filtering**: search by title/tags, filter by status
- **Data validation**: required fields, format validation, error messages
- **Navigation**: sidebar navigation, breadcrumbs, back button behavior
- **Responsive design**: mobile, tablet, desktop (Playwright can test multiple viewports)
- **Accessibility**: keyboard navigation, screen reader compatibility (via aria-labels)
- **Edge cases**: empty states, long text, special characters, rapid clicks

### 4. Run tests with specific options

For faster iteration during development:

```bash
# Run only tests matching a pattern
pnpm exec playwright test --grep "auth"

# Run a single test file
pnpm exec playwright test tests/e2e/auth.spec.ts

# Run with headed mode (see browser UI)
pnpm exec playwright test --headed

# Run with debug mode (pause and inspect)
pnpm exec playwright test --debug
```

### 5. Check test output and reports

Playwright generates HTML reports:

```bash
# View the report
pnpm exec playwright show-report
```

This opens an interactive report in the browser showing:
- Pass/fail for each test
- Screenshots and videos for failed tests
- Timing for each step
- Error messages and stack traces

### 6. Validate test fixtures and data

Ensure tests use consistent, isolated data:

- **Demo account**: tests should create test users via API before each test (or use the seeded demo account)
- **Isolation**: each test should be independent; no reliance on prior test state
- **Cleanup**: tests should clean up after themselves (delete created records) or use transactions that roll back
- **Fixtures**: Playwright fixtures (in `playwright.config.ts`) should set up common scenarios (logged-in user, empty project list, sample projects)

Example fixture pattern:

```typescript
// playwright.config.ts
export const test = base.extend({
  authenticatedPage: async ({ page }, use) => {
    // Login before each test
    await page.goto('http://localhost:5173/login');
    await page.fill('input[name="username"]', 'demo');
    await page.fill('input[name="password"]', 'demo');
    await page.click('button:has-text("Sign In")');
    await page.waitForURL('**/projects');
    await use(page);
    // Cleanup after each test (if needed)
  },
});
```

### 7. Report results

Summarize the test run:

```
E2E Test Results
================

Environment:
  Backend: http://localhost:8000/api ✓
  Frontend: http://localhost:5173 ✓

Test Suite:
  Total tests: <N>
  Passed: <N>
  Failed: <N>
  Skipped: <N>

Execution time: <Xs>

Failed tests (if any):
  - <test name>: <error message>
  - <test name>: <error message>

Coverage areas validated:
  ✓ Authentication (login, logout, token expiry)
  ✓ Project CRUD (create, read, update, delete)
  ✓ Interview workflow (capture, organize, triage)
  ✓ Search and filtering
  ✓ Navigation and UI
  ✓ Accessibility (keyboard, aria labels)
  ✓ Responsive design (mobile, tablet, desktop)

Edge cases tested:
  - Empty states (no projects, no interviews)
  - Long text input (titles, descriptions)
  - Special characters (quotes, unicode)
  - Rapid user interactions (double-click, fast navigation)
  - Concurrent operations (if applicable)

Status: [✓ PASS | ⚠ WARNINGS | X FAIL]
  If PASS: all tests passed, ready for review/release
  If WARNINGS: some tests flaky or warnings issued, review needed
  If FAIL: blocking issues, fixes required
```

## Test structure (when tests are added)

Create tests in `frontend/tests/e2e/`:

```
tests/e2e/
  ├── auth.spec.ts         (login, logout, token expiry)
  ├── projects.spec.ts     (CRUD for projects)
  ├── interviews.spec.ts   (capture, organize, triage)
  ├── search.spec.ts       (search, filter, sort)
  ├── navigation.spec.ts   (sidebar, breadcrumbs, routes)
  ├── accessibility.spec.ts (keyboard, aria, screen readers)
  ├── responsive.spec.ts   (mobile, tablet, desktop viewports)
  └── edge-cases.spec.ts   (empty states, long text, special chars)
```

Each test file should:
- Use Playwright's `test` fixture (or custom fixtures from `playwright.config.ts`)
- Be self-contained (setup/teardown within the test)
- Use descriptive test names
- Include assertions for success and error states
- Avoid hardcoded waits; use `waitForURL`, `waitForSelector`, `waitForFunction`

## Troubleshooting

**Browsers not found:**
```bash
pnpm exec playwright install
pnpm exec playwright install-deps  # also install system dependencies
```

**Tests timeout:**
- Increase timeout in `playwright.config.ts`: `timeout: 30000` (30 seconds)
- Check if backend/frontend are running
- Check if network is slow (use `--headed` to watch what's happening)

**Backend API errors in tests:**
- Verify `VITE_API_BASE_URL` points to the correct backend
- Check that backend is initialized and seeded: `SEED_DEMO_DATA=true uv run python -m app.db.init_local`
- Check CORS settings in `backend/app/core/config.py` allow localhost:5173

**Flaky tests (intermittent failures):**
- Replace hardcoded waits (`await page.waitForTimeout(1000)`) with targeted waits (`await page.waitForSelector('.modal')`)
- Ensure fixtures properly isolate test data
- Use `test.slow()` to mark slow tests and extend their timeout

**Screenshot/video not captured:**
- Ensure `screenshot: 'only-on-failure'` in `playwright.config.ts`
- Ensure `video: 'retain-on-failure'` in `playwright.config.ts`
- Videos are saved to `test-results/` directory

## Tech debt and limitations

This skill does not yet:
- Test against deployed dev/prod environments (only local dev)
- Run on a schedule (CI integration planned)
- Perform load testing or performance profiling
- Test mobile-specific features (geolocation, notifications, etc.)
- Test with multiple browser engines (only Chromium by default; Firefox and WebKit can be enabled)

CI integration (run E2E on every deploy, on releases) is planned for future work.

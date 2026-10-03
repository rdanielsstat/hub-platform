import { defineConfig, devices } from '@playwright/test'

/**
 * E2E tests. The backend is never started here: run one on :8000 first,
 * either `uv run uvicorn app.main:app` (SQLite) or the Docker Compose
 * stack (`make docker-up`, Postgres). See frontend/README.md.
 *
 * Projects:
 *  - chromium: app.spec.ts (browser) and api.spec.ts (API only), against
 *    whichever backend is on :8000.
 *  - docker-compose: integration.spec.ts, written for the Compose stack.
 *    Its tests that stop, start or pause the Compose Postgres only run
 *    with E2E_DOCKER=1, and need the project run alone with one worker:
 *    `make test-e2e-docker` and CI do both.
 *
 * webServer starts the Vite dev server on :5173, pointed at E2E_API_URL
 * (default http://localhost:8000), or reuses one already running there
 * outside CI.
 */
const API_URL = process.env.E2E_API_URL ?? 'http://localhost:8000'

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'html',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  webServer: {
    command: 'pnpm exec vite --port 5173 --strictPort',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    env: { VITE_API_BASE_URL: API_URL },
    timeout: 60_000,
  },
  projects: [
    {
      name: 'chromium',
      testIgnore: /integration\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'docker-compose',
      testMatch: /integration\.spec\.ts/,
      // In file order: the outage tests stop Postgres under everything
      // else. Run with --workers=1 so no other file runs meanwhile.
      fullyParallel: false,
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})

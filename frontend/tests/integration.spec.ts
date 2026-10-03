import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { test, expect, type Page } from '@playwright/test'
import {
  API_URL,
  PASSWORD,
  apiRoute,
  bearer,
  createProjectViaApi,
  registerViaApi,
  signInAs,
  uid,
  uniqueEmail,
  waitForApi,
} from './helpers'

/**
 * End-to-end tests for the Docker Compose stack: the Postgres-backed app
 * on :8000 (`make docker-up`) and Vite on :5173. Run as the
 * `docker-compose` Playwright project (`make test-e2e-docker`).
 *
 * Most tests here only need some backend on :8000. The "database outage"
 * ones stop, start or pause the Compose `postgres` service with the docker
 * CLI, so they only run with E2E_DOCKER=1. They take the database away
 * from every other test while they run, so run this project on its own
 * with one worker: `make test-e2e-docker` and CI do.
 */

const REPO_ROOT = fileURLToPath(new URL('../..', import.meta.url))
const DOCKER = process.env.E2E_DOCKER === '1'

function compose(...args: string[]): void {
  execFileSync('docker', ['compose', ...args], {
    cwd: REPO_ROOT,
    stdio: 'pipe',
    timeout: 60_000,
  })
}

async function waitForApiHealthyWithDatabase(page: Page): Promise<void> {
  // /health doesn't touch the database, so poll a sign-up, which does.
  await expect
    .poll(
      async () => {
        const user = await registerViaApi(page.request).catch(() => null)
        return user !== null
      },
      { timeout: 60_000, intervals: [500, 1000, 2000] },
    )
    .toBe(true)
}

const unreachable = (page: Page) =>
  page.getByRole('heading', { name: 'Can’t reach the server' })

test.describe('compose stack: full journey', () => {
  test('sign up, capture, note, reload, sign out, sign back in', async ({
    page,
  }) => {
    const email = uniqueEmail()
    const name = `Compose idea ${uid()}`

    await page.goto('/signup')
    await page.locator('#signup-email').fill(email)
    await page.locator('#signup-password').fill(PASSWORD)
    const registered = waitForApi(page, 'POST', '/auth/register')
    await page.getByRole('button', { name: 'Sign up' }).click()
    expect((await registered).status()).toBe(201)
    await expect(page.getByRole('heading', { name: 'Ideas' })).toBeVisible()

    await page
      .getByRole('banner')
      .getByRole('button', { name: 'Quick capture' })
      .click()
    const dialog = page.getByRole('dialog', { name: 'Quick capture' })
    await dialog.locator('#qc-name').fill(name)
    const created = waitForApi(page, 'POST', '/projects')
    await dialog.getByRole('button', { name: 'Capture', exact: true }).click()
    const project = (await (await created).json()) as { id: string }

    await page.goto(`/project/${project.id}`)
    const noteBox = page.getByPlaceholder('Add a note, thought, or update…')
    await noteBox.fill('Persisted in Postgres 🐘')
    const added = waitForApi(page, 'POST', `/projects/${project.id}/notes`)
    await page.getByRole('button', { name: 'Add note' }).click()
    expect((await added).status()).toBe(201)

    // A full reload: everything comes back from the database, and the
    // session cookie keeps the user signed in.
    await page.reload()
    await expect(page.getByText('Persisted in Postgres 🐘')).toBeVisible()

    await page.goto('/')
    await page.getByRole('button', { name: 'Sign out' }).click()
    await expect(page.locator('#login-email')).toBeVisible()

    await page.locator('#login-email').fill(email.toUpperCase())
    await page.locator('#login-password').fill(PASSWORD)
    await page.getByRole('button', { name: 'Log in' }).click()
    await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()
  })
})

test.describe('compose stack: API on Postgres', () => {
  test('stores and returns unicode, JSON and dates unchanged', async ({
    request,
  }) => {
    const user = await registerViaApi(request)
    const seed = {
      name: `Ünïcödé 日本語 🚀 ${uid()}`,
      tags: ['naïve', 'emoji 🚀'],
      targetDate: '2026-12-31',
      links: [{ label: 'Docs', url: 'https://example.com/a?b=c' }],
      status: 'Exploring',
    }

    const created = await createProjectViaApi(request, user, seed)
    const res = await request.get(`${API_URL}/projects/${created.id}`, {
      headers: bearer(user.token),
    })

    expect(await res.json()).toMatchObject(seed)
  })

  test('accepts frontend error reports', async ({ request }) => {
    const res = await request.post(`${API_URL}/client-errors`, {
      data: { kind: 'error', message: `e2e report ${uid()}` },
    })

    expect(res.status()).toBe(204)
  })
})

test.describe('compose stack: error reporting from the browser', () => {
  test('a failed API call is reported to /client-errors', async ({
    page,
    request,
  }) => {
    const user = await registerViaApi(request)
    await signInAs(page, user)
    await page.route(apiRoute('/projects'), (route) =>
      route.request().method() === 'GET'
        ? route.fulfill({ status: 503, json: { detail: 'Unavailable' } })
        : route.fallback(),
    )

    const report = page.waitForRequest(
      (req) =>
        req.method() === 'POST' &&
        new URL(req.url()).pathname === '/client-errors',
    )
    await page.goto('/')

    expect((await report).postDataJSON()).toMatchObject({
      kind: 'http',
      method: 'GET',
      status: 503,
    })
  })
})

test.describe('compose stack: session check survives backend trouble', () => {
  test('a failed session check is retried, not treated as signed out', async ({
    page,
    request,
  }) => {
    const user = await registerViaApi(request)
    await signInAs(page, user)
    // Fail every session check for 300 ms after the first one. Dev mode's
    // StrictMode runs the check twice on mount, so failing only the first
    // request would pass even without a retry; the window catches both,
    // and only the retry (500 ms later) gets through.
    let firstAt: number | undefined
    let calls = 0
    await page.route(apiRoute('/auth/me'), (route) => {
      calls += 1
      firstAt ??= Date.now()
      return Date.now() - firstAt < 300
        ? route.fulfill({ status: 503, json: { detail: 'Waking up' } })
        : route.fallback()
    })

    await page.goto('/')

    await expect(page.getByRole('heading', { name: 'Ideas' })).toBeVisible()
    await expect(page.locator('#login-email')).toHaveCount(0)
    expect(calls).toBeGreaterThanOrEqual(2)
  })

  test('an unreachable backend shows a retry screen, not the login page', async ({
    page,
    request,
  }) => {
    const user = await registerViaApi(request)
    await signInAs(page, user)
    await page.route(apiRoute('/auth/me'), (route) => route.abort())

    await page.goto('/')

    await expect(unreachable(page)).toBeVisible()
    await expect(page.locator('#login-email')).toHaveCount(0)

    await page.unroute(apiRoute('/auth/me'))
    await page.getByRole('button', { name: 'Try again' }).click()
    await expect(page.getByRole('heading', { name: 'Ideas' })).toBeVisible()
  })
})

test.describe('compose stack: database outage', () => {
  test.skip(!DOCKER, 'Set E2E_DOCKER=1 to let tests stop and start Postgres.')
  test.describe.configure({ mode: 'serial' })

  test.afterEach(() => {
    // Whatever happened, leave the database running for the next test.
    // Both fail harmlessly when it's already unpaused and running.
    for (const action of ['unpause', 'start']) {
      try {
        compose(action, 'postgres')
      } catch {
        // not paused / already started
      }
    }
  })

  test('Postgres down: retry screen, then back in once it returns', async ({
    page,
    request,
  }) => {
    const user = await registerViaApi(request)
    await signInAs(page, user)
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Ideas' })).toBeVisible()

    compose('stop', 'postgres')
    try {
      await page.reload()
      await expect(unreachable(page)).toBeVisible({ timeout: 30_000 })
      await expect(page.locator('#login-email')).toHaveCount(0)
    } finally {
      compose('start', 'postgres')
    }
    await waitForApiHealthyWithDatabase(page)

    await page.getByRole('button', { name: 'Try again' }).click()
    await expect(page.getByRole('heading', { name: 'Ideas' })).toBeVisible()
  })

  test('a slow, waking database (simulated Neon sleep) just delays the page', async ({
    page,
    request,
  }) => {
    const user = await registerViaApi(request)
    await signInAs(page, user)

    // Paused, Postgres accepts connections but answers nothing, like a
    // Neon compute that's still starting. Unpause shortly after the page
    // starts its session check.
    compose('pause', 'postgres')
    const resume = new Promise<void>((resolve) =>
      setTimeout(() => {
        compose('unpause', 'postgres')
        resolve()
      }, 2_000),
    )
    await page.goto('/')
    await resume

    await expect(page.getByRole('heading', { name: 'Ideas' })).toBeVisible({
      timeout: 30_000,
    })
    await expect(page.locator('#login-email')).toHaveCount(0)
  })
})

import { createHmac, randomUUID } from 'node:crypto'
import {
  expect,
  type APIRequestContext,
  type Page,
  type Response,
  type Route,
} from '@playwright/test'

/**
 * Shared helpers for the E2E suites (app.spec.ts, api.spec.ts). Both run
 * against the real local servers: Vite on :5173 (playwright.config.ts
 * baseURL) and uvicorn on :8000.
 *
 * Locally the API routers have no /api prefix; that only exists behind
 * CloudFront in AWS, where Mangum strips it. frontend/.env sets
 * VITE_API_BASE_URL=http://localhost:8000 to match.
 */
export const API_URL = process.env.E2E_API_URL ?? 'http://localhost:8000'
export const PASSWORD = 'e2e-password-123'

/** Short unique suffix for names, so parallel workers never collide. */
export function uid(): string {
  return randomUUID().slice(0, 8)
}

export function uniqueEmail(): string {
  return `e2e-${randomUUID()}@example.com`
}

/** A YYYY-MM-DD date `days` from today, in local time like the app uses. */
export function isoDateFromToday(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}

export function bearer(token: string) {
  return { Authorization: `Bearer ${token}` }
}

// --- API setup -------------------------------------------------------------

export interface TestUser {
  id: string
  email: string
  token: string
}

/** Register straight against the API; faster than the UI for setup. */
export async function registerViaApi(
  request: APIRequestContext,
  displayName?: string,
): Promise<TestUser> {
  const email = uniqueEmail()
  const res = await request.post(`${API_URL}/auth/register`, {
    data: { email, password: PASSWORD, displayName },
  })
  expect(res.status()).toBe(201)
  const { access_token: token } = (await res.json()) as {
    access_token: string
  }
  const me = await request.get(`${API_URL}/auth/me`, {
    headers: bearer(token),
  })
  const { id } = (await me.json()) as { id: string }
  return { id, email, token }
}

export interface ProjectSeed {
  name: string
  pitch?: string
  description?: string
  status?: string
  tags?: string[]
  excitement?: number
  effort?: number
  potential?: number
  nextAction?: string
  targetDate?: string | null
  links?: { label?: string; url: string }[]
}

export interface ApiProject {
  id: string
  name: string
  pitch: string
  description: string
  status: string
  tags: string[]
  excitement: number
  effort: number
  potential: number
  nextAction: string
  targetDate: string | null
  links: { label: string | null; url: string }[]
  createdAt: string
  updatedAt: string
}

export interface ApiNote {
  id: string
  projectId: string
  body: string
  createdAt: string
}

export async function createProjectViaApi(
  request: APIRequestContext,
  user: TestUser,
  seed: ProjectSeed,
): Promise<ApiProject> {
  const res = await request.post(`${API_URL}/projects`, {
    headers: bearer(user.token),
    data: seed,
  })
  expect(res.status()).toBe(201)
  return (await res.json()) as ApiProject
}

export async function getProjectViaApi(
  request: APIRequestContext,
  user: TestUser,
  id: string,
) {
  return request.get(`${API_URL}/projects/${id}`, {
    headers: bearer(user.token),
  })
}

export async function addNoteViaApi(
  request: APIRequestContext,
  user: TestUser,
  projectId: string,
  body: string,
): Promise<ApiNote> {
  const res = await request.post(`${API_URL}/projects/${projectId}/notes`, {
    headers: bearer(user.token),
    data: { body },
  })
  expect(res.status()).toBe(201)
  return ((await res.json()) as { note: ApiNote }).note
}

export async function listNotesViaApi(
  request: APIRequestContext,
  user: TestUser,
  projectId: string,
): Promise<ApiNote[]> {
  const res = await request.get(`${API_URL}/projects/${projectId}/notes`, {
    headers: bearer(user.token),
  })
  expect(res.status()).toBe(200)
  return (await res.json()) as ApiNote[]
}

// --- JWT forging -----------------------------------------------------------

/**
 * The local server signs tokens with HS256 and, unless HUB_JWT_SECRET is
 * set, the built-in dev secret (backend/app/core/config.py). Forging
 * tokens lets tests cover expiry and bad subjects without waiting an hour.
 * Override with E2E_JWT_SECRET if the server runs with another secret;
 * tests that need forging skip themselves when the secret doesn't match.
 */
const JWT_SECRET =
  process.env.E2E_JWT_SECRET ?? 'dev-only-insecure-secret-change-me'

function b64url(input: Buffer | string): string {
  return Buffer.from(input).toString('base64url')
}

export function forgeToken(
  payload: Record<string, unknown>,
  secret: string = JWT_SECRET,
): string {
  const header = b64url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const body = b64url(JSON.stringify(payload))
  const sig = createHmac('sha256', secret)
    .update(`${header}.${body}`)
    .digest('base64url')
  return `${header}.${body}.${sig}`
}

/** True when a forged, unexpired token is accepted by the running server. */
export async function canForgeTokens(
  request: APIRequestContext,
  user: TestUser,
): Promise<boolean> {
  const token = forgeToken({
    sub: user.id,
    exp: Math.floor(Date.now() / 1000) + 300,
  })
  const res = await request.get(`${API_URL}/auth/me`, {
    headers: bearer(token),
  })
  return res.status() === 200
}

// --- browser helpers -------------------------------------------------------

/**
 * Wait for one backend call. Match on method + exact pathname, since
 * response URLs are absolute (http://localhost:8000/...) and endsWith
 * would also match e.g. /projects/:id/notes for "/projects".
 */
export function waitForApi(
  page: Page,
  method: string,
  path: string | RegExp,
): Promise<Response> {
  return page.waitForResponse((res) => {
    if (res.request().method() !== method) return false
    const { pathname } = new URL(res.url())
    return typeof path === 'string' ? pathname === path : path.test(pathname)
  })
}

/** Glob for page.route() that matches one backend path exactly. */
export function apiRoute(path: string): string {
  return `${API_URL}${path}`
}

/**
 * Hold matching requests until release() is called, so a test can assert
 * on the in-flight UI (disabled buttons, skeletons) deterministically
 * instead of racing a fast local server.
 */
export async function holdRequests(
  page: Page,
  path: string,
  method: string,
): Promise<{ release: () => void; held: Promise<void> }> {
  let release!: () => void
  const gate = new Promise<void>((resolve) => (release = resolve))
  let markHeld!: () => void
  const held = new Promise<void>((resolve) => (markHeld = resolve))
  await page.route(apiRoute(path), async (route: Route) => {
    if (route.request().method() !== method) return route.fallback()
    markHeld()
    await gate
    await route.continue()
  })
  return { release, held }
}

/** Name of the httpOnly session cookie the API sets on login/register. */
export const SESSION_COOKIE = 'hub_token'

/**
 * Sign the browser in without going through the login form, by putting
 * the user's token in the session cookie the API would have set. Cookies
 * ignore ports, so a cookie for localhost reaches uvicorn on :8000 from
 * the app on :5173. It goes on the whole context, so every page in it is
 * signed in, like real tabs.
 */
export async function signInAs(page: Page, user: TestUser): Promise<void> {
  await setSessionCookie(page, user.token)
}

/** Put any value in the session cookie, e.g. a garbage or expired token. */
export async function setSessionCookie(
  page: Page,
  value: string,
): Promise<void> {
  await page.context().addCookies([
    {
      name: SESSION_COOKIE,
      value,
      domain: 'localhost',
      path: '/',
      httpOnly: true,
      sameSite: 'Strict',
    },
  ])
}

/** The session cookie as the browser holds it, or undefined. */
export async function sessionCookie(page: Page) {
  return (await page.context().cookies()).find((c) => c.name === SESSION_COOKIE)
}

/**
 * Open the dashboard and wait until the store's initial GET /projects has
 * landed. Until then the dashboard shows skeleton cards, so asserting on
 * card contents earlier would race the fetch.
 */
export async function openDashboard(page: Page): Promise<void> {
  const loaded = waitForApi(page, 'GET', '/projects')
  await page.goto('/')
  expect((await loaded).status()).toBe(200)
  await expect(page.getByRole('heading', { name: 'Ideas' })).toBeVisible()
}

/**
 * Open a project's detail page by URL. The page renders from the store,
 * which loads every project first, so wait for that before asserting.
 */
export async function openProject(page: Page, id: string): Promise<void> {
  const loaded = waitForApi(page, 'GET', '/projects')
  const notes = waitForApi(page, 'GET', `/projects/${id}/notes`)
  await page.goto(`/project/${id}`)
  await loaded
  await notes
}

/** Project cards are links to /project/:id with the name in an <h3>. */
export function cardTitles(page: Page) {
  return page.locator('main a[href^="/project/"] h3')
}

export function card(page: Page, name: string) {
  return page.locator('main a[href^="/project/"]').filter({
    has: page.getByRole('heading', { name, exact: true }),
  })
}

/**
 * Status filter pills render "<Status><count>" as two text nodes, so the
 * accessible name is e.g. "Active 2" (or "Active2"). Match on the prefix.
 */
export function statusPill(page: Page, label: string) {
  return page.getByRole('button', { name: new RegExp(`^${label}\\s*\\d+$`) })
}

/**
 * The detail page's name field is an unlabeled <input>; it's the first
 * input in <main> (the next-action field above it is a <textarea>).
 * Callers should assert its value before relying on it.
 */
export function detailNameInput(page: Page) {
  return page.locator('main input').first()
}

/** Error toasts render their message as the toast title. */
export function toast(page: Page, message: string) {
  return page.getByText(message, { exact: true })
}

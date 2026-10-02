import { test, expect, type Page } from '@playwright/test'
import {
  API_URL,
  PASSWORD,
  addNoteViaApi,
  apiRoute,
  bearer,
  card,
  cardTitles,
  createProjectViaApi,
  detailNameInput,
  getProjectViaApi,
  holdRequests,
  isoDateFromToday,
  listNotesViaApi,
  openDashboard,
  openProject,
  registerViaApi,
  sessionCookie,
  setSessionCookie,
  signInAs,
  statusPill,
  toast,
  uid,
  uniqueEmail,
  waitForApi,
  type ApiProject,
  type TestUser,
} from './helpers'

/**
 * Browser E2E tests against the real local stack: Vite on :5173 and
 * uvicorn on :8000. Each test registers its own user through the API, so
 * tests are isolated and run in parallel. The UI is only driven for the
 * flow under test; setup (users, seed projects, notes) goes straight to
 * the API.
 *
 * Error states use page.route() to make one specific backend call fail.
 * That's the only mocking here; everything else hits the real backend.
 */

// --- shared UI steps -------------------------------------------------------

async function logInViaForm(page: Page, user: TestUser) {
  await page.goto('/login')
  await page.locator('#login-email').fill(user.email)
  await page.locator('#login-password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Log in' }).click()
  await expect(page.getByRole('heading', { name: 'Ideas' })).toBeVisible()
}

async function goToSignup(page: Page) {
  await page.goto('/signup')
  // Wait for the signup form itself before touching inputs: after a
  // client-side navigation the URL updates before React swaps routes, so
  // the outgoing login form can still be on screen briefly.
  await expect(page.locator('#signup-email')).toBeVisible()
}

/** The header's capture button (the empty state has a second one). */
function headerCapture(page: Page) {
  return page.getByRole('banner').getByRole('button', { name: 'Quick capture' })
}

/** base-ui keeps the dialog mounted; scope every query to it. */
function captureDialog(page: Page) {
  return page.getByRole('dialog', { name: 'Quick capture' })
}

async function quickCapture(page: Page, name: string) {
  await headerCapture(page).click()
  const dialog = captureDialog(page)
  await dialog.locator('#qc-name').fill(name)
  const created = waitForApi(page, 'POST', '/projects')
  // exact: the footer also has "Capture & open".
  await dialog.getByRole('button', { name: 'Capture', exact: true }).click()
  const res = await created
  expect(res.status()).toBe(201)
  await expect(dialog).toBeHidden()
  return (await res.json()) as ApiProject
}

/** Collect API requests matching method + path, for "nothing was sent" checks. */
function recordRequests(page: Page, method: string, path: string) {
  const seen: string[] = []
  page.on('request', (req) => {
    if (req.method() === method && new URL(req.url()).pathname === path) {
      seen.push(req.url())
    }
  })
  return seen
}

async function hasHorizontalScroll(page: Page): Promise<boolean> {
  return page.evaluate(
    () =>
      document.documentElement.scrollWidth >
      document.documentElement.clientWidth,
  )
}

// --- auth ------------------------------------------------------------------

test.describe('auth: signup', () => {
  test('signs up a new user and lands on the dashboard', async ({ page }) => {
    const email = uniqueEmail()
    const displayName = 'E2E User'

    // Logged out, every path renders the login page; its footer links to /signup.
    await page.goto('/login')
    await page.getByRole('link', { name: 'Sign up' }).click()
    await expect(page).toHaveURL('/signup')

    // Ids, not labels: the URL changes before React swaps routes, so a bare
    // "Email" label can still match the outgoing login form's input.
    await page.locator('#signup-email').fill(email)
    await page.locator('#signup-name').fill(displayName)
    await page.locator('#signup-password').fill(PASSWORD)

    const registered = waitForApi(page, 'POST', '/auth/register')
    await page.getByRole('button', { name: 'Sign up' }).click()
    const res = await registered
    expect(res.status()).toBe(201)
    expect(res.request().postDataJSON()).toEqual({
      email,
      password: PASSWORD,
      displayName,
    })

    // The dashboard is the authenticated "/" route.
    await expect(page).toHaveURL('/')
    await expect(page.getByRole('heading', { name: 'Ideas' })).toBeVisible()
    await expect(page.getByText(displayName)).toBeVisible()
    await expect(page.getByText('Nothing captured yet')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
  })

  test('without a display name the header shows the email, and blank is omitted', async ({
    page,
  }) => {
    const email = uniqueEmail()
    await goToSignup(page)
    await page.locator('#signup-email').fill(email)
    // Whitespace-only display name is trimmed to "not provided".
    await page.locator('#signup-name').fill('   ')
    await page.locator('#signup-password').fill(PASSWORD)

    const registered = waitForApi(page, 'POST', '/auth/register')
    await page.getByRole('button', { name: 'Sign up' }).click()
    expect((await registered).request().postDataJSON()).toEqual({
      email,
      password: PASSWORD,
    })
    await expect(page.getByRole('banner').getByText(email)).toBeVisible()
  })

  test('submit stays disabled until email is filled and password has 8+ characters', async ({
    page,
  }) => {
    await goToSignup(page)
    const submit = page.getByRole('button', { name: 'Sign up' })

    await expect(submit).toBeDisabled()
    await page.locator('#signup-email').fill(uniqueEmail())
    await expect(submit).toBeDisabled()
    await page.locator('#signup-password').fill('1234567')
    await expect(submit).toBeDisabled()
    await page.locator('#signup-password').fill('12345678')
    await expect(submit).toBeEnabled()

    // A whitespace-only email doesn't count as filled.
    await page.locator('#signup-email').fill('   ')
    await expect(submit).toBeDisabled()
  })

  test('the browser blocks a malformed email before any request', async ({
    page,
  }) => {
    const registers = recordRequests(page, 'POST', '/auth/register')
    await goToSignup(page)
    await page.locator('#signup-email').fill('not-an-email')
    await page.locator('#signup-password').fill(PASSWORD)
    await page.getByRole('button', { name: 'Sign up' }).click()

    // type="email" native validation stops the submit event.
    expect(
      await page
        .locator('#signup-email')
        .evaluate((el) => (el as HTMLInputElement).validity.typeMismatch),
    ).toBe(true)
    await expect(page).toHaveURL('/signup')
    expect(registers).toHaveLength(0)
  })

  test('an email the browser accepts but the API rejects shows the API error', async ({
    page,
  }) => {
    // "user@localhost" passes the browser's type="email" check but not
    // the backend's EmailStr (no domain dot), so it round-trips to a 422.
    await goToSignup(page)
    await page.locator('#signup-email').fill(`e2e-${uid()}@localhost`)
    await page.locator('#signup-password').fill(PASSWORD)

    const registered = waitForApi(page, 'POST', '/auth/register')
    await page.getByRole('button', { name: 'Sign up' }).click()
    expect((await registered).status()).toBe(422)

    await expect(page.getByRole('alert')).toContainText(
      'value is not a valid email address',
    )
    // Form is usable again after the error.
    await expect(page.getByRole('button', { name: 'Sign up' })).toBeEnabled()
  })

  test('an already-registered email shows the 409 message', async ({
    page,
    request,
  }) => {
    const existing = await registerViaApi(request)
    await goToSignup(page)
    // Different casing: the backend treats emails case-insensitively.
    await page.locator('#signup-email').fill(existing.email.toUpperCase())
    await page.locator('#signup-password').fill(PASSWORD)

    const registered = waitForApi(page, 'POST', '/auth/register')
    await page.getByRole('button', { name: 'Sign up' }).click()
    expect((await registered).status()).toBe(409)

    await expect(page.getByRole('alert')).toHaveText('Email already registered')
    await expect(page).toHaveURL('/signup')
  })

  test('the button is disabled while the request is in flight', async ({
    page,
  }) => {
    const { release, held } = await holdRequests(page, '/auth/register', 'POST')
    await goToSignup(page)
    await page.locator('#signup-email').fill(uniqueEmail())
    await page.locator('#signup-password').fill(PASSWORD)
    const submit = page.getByRole('button', { name: 'Sign up' })
    await submit.click()

    await held
    await expect(submit).toBeDisabled()
    release()
    await expect(page.getByRole('heading', { name: 'Ideas' })).toBeVisible()
  })

  test('a network failure shows a generic message', async ({ page }) => {
    await page.route(apiRoute('/auth/register'), (route) => route.abort())
    await goToSignup(page)
    await page.locator('#signup-email').fill(uniqueEmail())
    await page.locator('#signup-password').fill(PASSWORD)
    await page.getByRole('button', { name: 'Sign up' }).click()
    await expect(page.getByRole('alert')).toHaveText('Something went wrong.')
  })

  test('links back to login', async ({ page }) => {
    await goToSignup(page)
    await page.getByRole('link', { name: 'Log in' }).click()
    await expect(page.locator('#login-email')).toBeVisible()
  })
})

test.describe('auth: login', () => {
  test('logs in an existing user', async ({ page, request }) => {
    const user = await registerViaApi(request)

    await page.goto('/login')
    await page.locator('#login-email').fill(user.email)
    await page.locator('#login-password').fill(PASSWORD)

    // Login is an OAuth2 password form post (username/password, urlencoded),
    // then GET /auth/me to load the user.
    const loggedIn = waitForApi(page, 'POST', '/auth/login')
    const me = waitForApi(page, 'GET', '/auth/me')
    await page.getByRole('button', { name: 'Log in' }).click()

    const loginRes = await loggedIn
    expect(loginRes.status()).toBe(200)
    expect(loginRes.request().postData()).toContain(
      `username=${encodeURIComponent(user.email)}`,
    )
    expect(await (await me).json()).toMatchObject({ email: user.email })

    await expect(page).toHaveURL('/')
    await expect(page.getByRole('heading', { name: 'Ideas' })).toBeVisible()
    // No display name was set, so the header falls back to the email.
    await expect(page.getByRole('banner').getByText(user.email)).toBeVisible()
    // The session is an httpOnly, SameSite=Strict cookie, out of reach of
    // page scripts, and nothing is left in localStorage.
    const cookie = await sessionCookie(page)
    expect(cookie?.value).toBeTruthy()
    expect(cookie?.httpOnly).toBe(true)
    expect(cookie?.sameSite).toBe('Strict')
    expect(await page.evaluate(() => document.cookie)).not.toContain(
      'hub_token',
    )
    expect(
      await page.evaluate(() => Object.values(localStorage)),
    ).not.toContain(cookie?.value)
  })

  test('rejects a wrong password with an inline error', async ({
    page,
    request,
  }) => {
    const user = await registerViaApi(request)

    await page.goto('/login')
    await page.locator('#login-email').fill(user.email)
    await page.locator('#login-password').fill('not-the-password')

    const loggedIn = waitForApi(page, 'POST', '/auth/login')
    await page.getByRole('button', { name: 'Log in' }).click()
    expect((await loggedIn).status()).toBe(401)

    await expect(page.getByRole('alert')).toHaveText(
      'Incorrect email or password',
    )
    await expect(page).toHaveURL('/login')
    // A failed login must not trigger the "session expired" logout path
    // or leave a session cookie behind.
    expect(await sessionCookie(page)).toBeUndefined()

    // Retrying with the right password clears the error and logs in.
    await page.locator('#login-password').fill(PASSWORD)
    await page.getByRole('button', { name: 'Log in' }).click()
    await expect(page.getByRole('heading', { name: 'Ideas' })).toBeVisible()
  })

  test('an unknown email gets the same message as a wrong password', async ({
    page,
  }) => {
    await page.goto('/login')
    await page.locator('#login-email').fill(uniqueEmail())
    await page.locator('#login-password').fill(PASSWORD)
    await page.getByRole('button', { name: 'Log in' }).click()
    await expect(page.getByRole('alert')).toHaveText(
      'Incorrect email or password',
    )
  })

  test('submit stays disabled until both fields are filled', async ({
    page,
  }) => {
    await page.goto('/login')
    const submit = page.getByRole('button', { name: 'Log in' })
    await expect(submit).toBeDisabled()
    await page.locator('#login-email').fill(uniqueEmail())
    await expect(submit).toBeDisabled()
    // Unlike signup, login has no length rule: any non-empty password.
    await page.locator('#login-password').fill('x')
    await expect(submit).toBeEnabled()
  })

  test('the button is disabled while the request is in flight', async ({
    page,
    request,
  }) => {
    const user = await registerViaApi(request)
    const { release, held } = await holdRequests(page, '/auth/login', 'POST')
    await page.goto('/login')
    await page.locator('#login-email').fill(user.email)
    await page.locator('#login-password').fill(PASSWORD)
    const submit = page.getByRole('button', { name: 'Log in' })
    await submit.click()

    await held
    await expect(submit).toBeDisabled()
    release()
    await expect(page.getByRole('heading', { name: 'Ideas' })).toBeVisible()
  })
})

test.describe('auth: session', () => {
  test('signing out returns to login and clears the token', async ({
    page,
    request,
  }) => {
    const user = await registerViaApi(request)
    // Through the form rather than signInAs(), so this covers the cookie
    // the API sets as well as the one it clears.
    await logInViaForm(page, user)

    await page.getByRole('button', { name: 'Sign out' }).click()

    await expect(page.locator('#login-email')).toBeVisible()
    // Page scripts can't delete an httpOnly cookie; POST /auth/logout did.
    await expect.poll(() => sessionCookie(page)).toBeUndefined()

    // And stays signed out across a reload.
    await page.reload()
    await expect(page.locator('#login-email')).toBeVisible()
  })

  test('the session survives a reload', async ({ page, request }) => {
    const user = await registerViaApi(request)
    await logInViaForm(page, user)

    const me = waitForApi(page, 'GET', '/auth/me')
    await page.reload()
    expect((await me).status()).toBe(200)
    await expect(page.getByRole('heading', { name: 'Ideas' })).toBeVisible()
    await expect(page.getByRole('banner').getByText(user.email)).toBeVisible()
  })

  test('without a token, any app URL shows the login page', async ({
    page,
  }) => {
    // There's no redirect: the logged-out route table renders LoginPage
    // for every path except /signup, and the URL is left as-is.
    for (const path of ['/', '/project/some-id', '/no-such-page']) {
      await page.goto(path)
      await expect(page.locator('#login-email')).toBeVisible()
      await expect(page).toHaveURL(path)
    }
  })

  test('after logging in from a deep link, the app goes to the dashboard', async ({
    page,
    request,
  }) => {
    // Current behavior: login always navigates to "/", it doesn't return
    // to the URL the user originally asked for.
    const user = await registerViaApi(request)
    const project = await createProjectViaApi(request, user, { name: 'Deep' })
    await page.goto(`/project/${project.id}`)
    await page.locator('#login-email').fill(user.email)
    await page.locator('#login-password').fill(PASSWORD)
    await page.getByRole('button', { name: 'Log in' }).click()
    await expect(page).toHaveURL('/')
  })

  test('an invalid session cookie is cleared and shows login', async ({
    page,
  }) => {
    await page.goto('/login')
    await setSessionCookie(page, 'garbage')

    const me = waitForApi(page, 'GET', '/auth/me')
    await page.reload()
    expect((await me).status()).toBe(401)

    await expect(page.locator('#login-email')).toBeVisible()
    // The 401 that rejected it also expired it.
    expect(await sessionCookie(page)).toBeUndefined()
  })

  test('a 401 mid-session logs the user out without an error toast', async ({
    page,
    request,
  }) => {
    const user = await registerViaApi(request)
    await logInViaForm(page, user)

    // Simulate the session expiring while the app is open.
    await setSessionCookie(page, 'expired')
    await headerCapture(page).click()
    await captureDialog(page).locator('#qc-name').fill('Never saved')
    const created = waitForApi(page, 'POST', '/projects')
    await captureDialog(page)
      .getByRole('button', { name: 'Capture', exact: true })
      .click()
    expect((await created).status()).toBe(401)

    // The global 401 handler logs out; reportError skips 401s so there's
    // no confusing second message.
    await expect(page.locator('#login-email')).toBeVisible()
    await expect(page.getByText('Could not validate credentials')).toHaveCount(
      0,
    )
  })

  test('logged-in users visiting /login or /signup land on the dashboard', async ({
    page,
    request,
  }) => {
    const user = await registerViaApi(request)
    await signInAs(page, user)
    for (const path of ['/login', '/signup']) {
      await page.goto(path)
      await expect(page).toHaveURL('/')
      await expect(page.getByRole('heading', { name: 'Ideas' })).toBeVisible()
    }
  })

  test('an unknown route while logged in shows the not-found page', async ({
    page,
    request,
  }) => {
    const user = await registerViaApi(request)
    await signInAs(page, user)
    await page.goto(`/nope-${uid()}`)
    await expect(page.getByText('Nothing parked here')).toBeVisible()
  })
})

// --- dashboard -------------------------------------------------------------

test.describe('dashboard', () => {
  test('shows the empty state for a new user', async ({ page, request }) => {
    const user = await registerViaApi(request)
    await signInAs(page, user)

    const loaded = waitForApi(page, 'GET', '/projects')
    await page.goto('/')
    expect(await (await loaded).json()).toEqual([])

    await expect(page.getByText('Nothing captured yet')).toBeVisible()
    await expect(
      page.getByText('Capture your first idea to get started.'),
    ).toBeVisible()
    await expect(statusPill(page, 'All')).toHaveText(/0$/)
    await expect(cardTitles(page)).toHaveCount(0)

    // The empty state's own button opens quick capture.
    await page
      .getByRole('main')
      .getByRole('button', { name: 'Quick capture' })
      .click()
    await expect(captureDialog(page)).toBeVisible()
  })

  test('lists the user’s projects as cards', async ({ page, request }) => {
    const user = await registerViaApi(request)
    const id = uid()
    const first = await createProjectViaApi(request, user, {
      name: `Listed one ${id}`,
      pitch: 'First pitch',
      tags: ['alpha'],
    })
    const second = await createProjectViaApi(request, user, {
      name: `Listed two ${id}`,
      status: 'Active',
    })
    const third = await createProjectViaApi(request, user, {
      name: `Listed three ${id}`,
      description: 'Only a description',
    })
    await signInAs(page, user)

    const loaded = waitForApi(page, 'GET', '/projects')
    await page.goto('/')
    const listed = (await (await loaded).json()) as ApiProject[]
    expect(listed.map((p) => p.id).sort()).toEqual(
      [first.id, second.id, third.id].sort(),
    )

    await expect(cardTitles(page)).toHaveCount(3)
    const firstCard = card(page, first.name)
    await expect(firstCard).toContainText('First pitch')
    await expect(firstCard).toContainText('alpha')
    await expect(firstCard).toHaveAttribute('href', `/project/${first.id}`)
    // Card text falls back pitch → description → placeholder.
    await expect(card(page, third.name)).toContainText('Only a description')
    await expect(card(page, second.name)).toContainText('No pitch yet.')

    await expect(statusPill(page, 'All')).toHaveText(/3$/)
    await expect(statusPill(page, 'Inbox')).toHaveText(/2$/)
    await expect(statusPill(page, 'Active')).toHaveText(/1$/)
  })

  test('another user’s projects never appear', async ({ page, request }) => {
    const me = await registerViaApi(request)
    const other = await registerViaApi(request)
    await createProjectViaApi(request, other, { name: `Not mine ${uid()}` })
    const mine = await createProjectViaApi(request, me, {
      name: `Mine ${uid()}`,
    })
    await signInAs(page, me)
    await openDashboard(page)
    await expect(cardTitles(page)).toHaveText([mine.name])
  })

  test('shows skeleton cards while loading', async ({ page, request }) => {
    const user = await registerViaApi(request)
    await signInAs(page, user)
    const { release, held } = await holdRequests(page, '/projects', 'GET')

    await page.goto('/')
    await held
    await expect(page.locator('main .animate-pulse')).toHaveCount(6)
    await expect(page.getByText('Nothing captured yet')).toHaveCount(0)

    release()
    await expect(page.getByText('Nothing captured yet')).toBeVisible()
    await expect(page.locator('main .animate-pulse')).toHaveCount(0)
  })

  test('a failed load shows an error state that can retry', async ({
    page,
    request,
  }) => {
    const user = await registerViaApi(request)
    const project = await createProjectViaApi(request, user, {
      name: `Retry ${uid()}`,
    })
    await signInAs(page, user)

    await page.route(apiRoute('/projects'), (route) =>
      route.request().method() === 'GET'
        ? route.fulfill({ status: 500, json: { detail: 'Database is down' } })
        : route.fallback(),
    )
    await page.goto('/')
    await expect(page.getByText("Couldn't load your ideas")).toBeVisible()
    await expect(page.getByText('Database is down')).toBeVisible()
    // Stats and toolbar are hidden in the error state.
    await expect(statusPill(page, 'All')).toHaveCount(0)

    await page.unroute(apiRoute('/projects'))
    await page.getByRole('button', { name: 'Try again' }).click()
    await expect(card(page, project.name)).toBeVisible()
  })

  test('search matches name, pitch, description and tags', async ({
    page,
    request,
  }) => {
    const user = await registerViaApi(request)
    const id = uid()
    const byName = await createProjectViaApi(request, user, {
      name: `Zebra ${id}`,
    })
    const byPitch = await createProjectViaApi(request, user, {
      name: `P ${id}`,
      pitch: 'about giraffes',
    })
    const byDesc = await createProjectViaApi(request, user, {
      name: `D ${id}`,
      description: 'mentions an okapi',
    })
    const byTag = await createProjectViaApi(request, user, {
      name: `T ${id}`,
      tags: ['lemur'],
    })
    await signInAs(page, user)
    await openDashboard(page)

    const search = page.getByPlaceholder('Search ideas, pitches, tags…')
    // Case-insensitive.
    for (const [q, expected] of [
      ['ZEBRA', byName.name],
      ['giraffe', byPitch.name],
      ['okapi', byDesc.name],
      ['lemur', byTag.name],
    ] as const) {
      await search.fill(q)
      await expect(cardTitles(page)).toHaveText([expected])
    }

    await search.fill('no-such-thing')
    await expect(page.getByText('No matches')).toBeVisible()

    await page.getByRole('button', { name: 'Clear search' }).click()
    await expect(search).toHaveValue('')
    await expect(cardTitles(page)).toHaveCount(4)
  })

  test('quick-win badge and target-date countdowns', async ({
    page,
    request,
  }) => {
    const user = await registerViaApi(request)
    const id = uid()
    // Quick win: open status, excitement >= 4, effort <= 2.
    const quick = await createProjectViaApi(request, user, {
      name: `Quick ${id}`,
      excitement: 4,
      effort: 2,
    })
    // Same scores but Parked: not a quick win.
    const parked = await createProjectViaApi(request, user, {
      name: `Parked ${id}`,
      status: 'Parked',
      excitement: 5,
      effort: 1,
    })
    const soon = await createProjectViaApi(request, user, {
      name: `Soon ${id}`,
      targetDate: isoDateFromToday(5),
    })
    const late = await createProjectViaApi(request, user, {
      name: `Late ${id}`,
      targetDate: isoDateFromToday(-3),
    })
    await signInAs(page, user)
    await openDashboard(page)

    await expect(card(page, quick.name)).toContainText('Quick win')
    await expect(card(page, parked.name)).not.toContainText('Quick win')
    await expect(card(page, soon.name)).toContainText('5d')
    await expect(card(page, late.name)).toContainText('3d over')
  })

  test('long, unicode and markup-like names render as plain text', async ({
    page,
    request,
  }) => {
    const user = await registerViaApi(request)
    const longName = `Long ${'word '.repeat(80)}${uid()}`
    const unicode = `日本語 🚀 Ünïcödé ${uid()}`
    const markup = `<img src=x onerror="window.__xss=1"> ${uid()}`
    for (const name of [longName, unicode, markup]) {
      await createProjectViaApi(request, user, { name })
    }
    await signInAs(page, user)
    await openDashboard(page)

    await expect(card(page, longName.trim())).toBeVisible()
    await expect(card(page, unicode)).toBeVisible()
    await expect(card(page, markup)).toBeVisible()
    // React escapes it: shown as text, never executed.
    expect(await page.evaluate(() => 'xss' in window)).toBe(false)
    expect(await page.evaluate(() => '__xss' in window)).toBe(false)
    expect(await hasHorizontalScroll(page)).toBe(false)
  })
})

// --- create ----------------------------------------------------------------

test.describe('create project', () => {
  let user: TestUser

  test.beforeEach(async ({ page, request }) => {
    user = await registerViaApi(request)
    await signInAs(page, user)
    await openDashboard(page)
  })

  test('captures a project with full details', async ({ page, request }) => {
    await headerCapture(page).click()
    const dialog = captureDialog(page)
    await expect(dialog).toBeVisible()

    const name = `Captured ${uid()}`
    await dialog.locator('#qc-name').fill(name)
    await dialog.locator('#qc-pitch').fill('A pitch from E2E')

    // Status, tags, next action and scores live behind "More details".
    await dialog.getByRole('button', { name: 'More details' }).click()
    await dialog.locator('#qc-desc').fill('Brain dump text')
    await dialog.locator('#qc-status').selectOption('Exploring')
    // Tags are comma-separated, trimmed and lowercased; empties dropped.
    await dialog.locator('#qc-tags').fill(' E2E, , Alpha ,')
    await dialog.locator('#qc-next').fill('Write the first test')
    await dialog.getByRole('button', { name: 'Excitement 5 of 5' }).click()
    await dialog.getByRole('button', { name: 'Effort 2 of 5' }).click()
    await expect(
      dialog.getByRole('button', { name: 'Excitement 5 of 5' }),
    ).toHaveAttribute('aria-pressed', 'true')

    const created = waitForApi(page, 'POST', '/projects')
    await dialog.getByRole('button', { name: 'Capture', exact: true }).click()

    const res = await created
    expect(res.status()).toBe(201)
    expect(res.request().postDataJSON()).toEqual({
      name,
      pitch: 'A pitch from E2E',
      description: 'Brain dump text',
      status: 'Exploring',
      tags: ['e2e', 'alpha'],
      nextAction: 'Write the first test',
      excitement: 5,
      effort: 2,
      potential: 3,
    })
    const project = (await res.json()) as ApiProject

    await expect(dialog).toBeHidden()
    await expect(page).toHaveURL('/')
    const newCard = card(page, name)
    await expect(newCard).toBeVisible()
    await expect(newCard).toContainText('A pitch from E2E')
    await expect(newCard).toHaveAttribute('href', `/project/${project.id}`)
    await expect(statusPill(page, 'Exploring')).toHaveText(/1$/)

    // Persisted, not just in client state.
    const fetched = await getProjectViaApi(request, user, project.id)
    expect(await fetched.json()).toMatchObject({
      name,
      status: 'Exploring',
      tags: ['e2e', 'alpha'],
    })
  })

  test('"Capture & open" goes straight to the new project', async ({
    page,
  }) => {
    await headerCapture(page).click()
    const dialog = captureDialog(page)
    const name = `Opened ${uid()}`
    await dialog.locator('#qc-name').fill(name)

    const created = waitForApi(page, 'POST', '/projects')
    await dialog.getByRole('button', { name: 'Capture & open' }).click()
    const project = (await (await created).json()) as ApiProject

    await expect(page).toHaveURL(`/project/${project.id}`)
    await expect(detailNameInput(page)).toHaveValue(name)
  })

  test('Enter in the name field captures', async ({ page }) => {
    await headerCapture(page).click()
    const name = `Entered ${uid()}`
    await captureDialog(page).locator('#qc-name').fill(name)
    const created = waitForApi(page, 'POST', '/projects')
    await captureDialog(page).locator('#qc-name').press('Enter')
    expect((await created).status()).toBe(201)
    await expect(card(page, name)).toBeVisible()
  })

  test('capture buttons stay disabled for a blank or whitespace name', async ({
    page,
  }) => {
    const posts = recordRequests(page, 'POST', '/projects')
    await headerCapture(page).click()
    const dialog = captureDialog(page)
    const capture = dialog.getByRole('button', { name: 'Capture', exact: true })
    const captureOpen = dialog.getByRole('button', { name: 'Capture & open' })

    await expect(capture).toBeDisabled()
    await expect(captureOpen).toBeDisabled()
    await dialog.locator('#qc-pitch').fill('Pitch without a name')
    await expect(capture).toBeDisabled()
    await dialog.locator('#qc-name').fill('   ')
    await expect(capture).toBeDisabled()
    // Enter with a blank name does nothing either.
    await dialog.locator('#qc-name').press('Enter')
    await expect(dialog).toBeVisible()
    expect(posts).toHaveLength(0)
  })

  test('Cancel and Escape close without saving and reset the form', async ({
    page,
  }) => {
    const posts = recordRequests(page, 'POST', '/projects')
    const dialog = captureDialog(page)

    await headerCapture(page).click()
    await dialog.locator('#qc-name').fill('Draft')
    await dialog.getByRole('button', { name: 'More details' }).click()
    await dialog.getByRole('button', { name: 'Cancel' }).click()
    await expect(dialog).toBeHidden()

    await headerCapture(page).click()
    await expect(dialog.locator('#qc-name')).toHaveValue('')
    // "More details" collapsed again.
    await expect(dialog.locator('#qc-desc')).toHaveCount(0)
    await dialog.locator('#qc-name').fill('Draft 2')
    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()

    expect(posts).toHaveLength(0)
    await expect(page.getByText('Nothing captured yet')).toBeVisible()
  })

  test('buttons are disabled while saving', async ({ page }) => {
    const { release, held } = await holdRequests(page, '/projects', 'POST')
    await headerCapture(page).click()
    const dialog = captureDialog(page)
    await dialog.locator('#qc-name').fill(`Slow ${uid()}`)
    await dialog.getByRole('button', { name: 'Capture', exact: true }).click()

    await held
    await expect(
      dialog.getByRole('button', { name: 'Capture', exact: true }),
    ).toBeDisabled()
    await expect(
      dialog.getByRole('button', { name: 'Capture & open' }),
    ).toBeDisabled()
    release()
    await expect(dialog).toBeHidden()
  })

  test('an API error shows a toast and keeps the draft', async ({ page }) => {
    await page.route(apiRoute('/projects'), (route) =>
      route.request().method() === 'POST'
        ? route.fulfill({ status: 500, json: { detail: 'Server exploded' } })
        : route.fallback(),
    )
    await headerCapture(page).click()
    const dialog = captureDialog(page)
    const name = `Kept draft ${uid()}`
    await dialog.locator('#qc-name').fill(name)
    await dialog.getByRole('button', { name: 'Capture', exact: true }).click()

    // HttpError messages come from the backend's `detail`.
    await expect(toast(page, 'Server exploded')).toBeVisible()
    await expect(dialog).toBeVisible()
    await expect(dialog.locator('#qc-name')).toHaveValue(name)
    await expect(
      dialog.getByRole('button', { name: 'Capture', exact: true }),
    ).toBeEnabled()

    // Retry once the backend recovers.
    await page.unroute(apiRoute('/projects'))
    await dialog.getByRole('button', { name: 'Capture', exact: true }).click()
    await expect(dialog).toBeHidden()
    await expect(card(page, name)).toBeVisible()
  })

  test('a network failure shows the generic fallback toast', async ({
    page,
  }) => {
    await page.route(apiRoute('/projects'), (route) =>
      route.request().method() === 'POST' ? route.abort() : route.fallback(),
    )
    await headerCapture(page).click()
    await captureDialog(page).locator('#qc-name').fill('Offline')
    await captureDialog(page)
      .getByRole('button', { name: 'Capture', exact: true })
      .click()
    await expect(
      toast(page, "Couldn't create that project. Try again."),
    ).toBeVisible()
  })

  test('long and unicode values round-trip', async ({ page, request }) => {
    const name = `Ünïcödé 日本語 🚀 ${uid()}`
    const desc = `${'Lorem ipsum dolor sit amet. '.repeat(200)}\nSecond line ✓`
    await headerCapture(page).click()
    const dialog = captureDialog(page)
    await dialog.locator('#qc-name').fill(name)
    await dialog.getByRole('button', { name: 'More details' }).click()
    await dialog.locator('#qc-desc').fill(desc)
    await dialog.locator('#qc-tags').fill('Émoji-🚀, ÜBER')

    const created = waitForApi(page, 'POST', '/projects')
    await dialog.getByRole('button', { name: 'Capture', exact: true }).click()
    const project = (await (await created).json()) as ApiProject

    const saved = await (
      await getProjectViaApi(request, user, project.id)
    ).json()
    expect(saved).toMatchObject({
      name,
      description: desc,
      tags: ['émoji-🚀', 'über'],
    })
    await expect(card(page, name)).toBeVisible()
  })
})

// --- filter ----------------------------------------------------------------

test.describe('filter projects', () => {
  let names: { inbox: string; activeXY: string; activeY: string }

  test.beforeEach(async ({ page, request }) => {
    const user = await registerViaApi(request)
    const id = uid()
    names = {
      inbox: `Inbox x ${id}`,
      activeXY: `Active xy ${id}`,
      activeY: `Active y ${id}`,
    }
    await createProjectViaApi(request, user, {
      name: names.inbox,
      status: 'Inbox',
      tags: ['x'],
    })
    await createProjectViaApi(request, user, {
      name: names.activeXY,
      status: 'Active',
      tags: ['x', 'y'],
    })
    await createProjectViaApi(request, user, {
      name: names.activeY,
      status: 'Active',
      tags: ['y'],
    })
    await signInAs(page, user)
    await openDashboard(page)
    await expect(cardTitles(page)).toHaveCount(3)
  })

  // Filtering is client-side only (no API call), so these assert UI state.

  test('by status', async ({ page }) => {
    await statusPill(page, 'Active').click()
    await expect(statusPill(page, 'Active')).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    await expect(cardTitles(page)).toHaveCount(2)
    await expect(card(page, names.inbox)).toHaveCount(0)

    await statusPill(page, 'Inbox').click()
    await expect(cardTitles(page)).toHaveText([names.inbox])

    // A status with zero projects shows the no-matches state.
    await statusPill(page, 'Killed').click()
    await expect(page.getByText('No matches')).toBeVisible()

    await statusPill(page, 'All').click()
    await expect(cardTitles(page)).toHaveCount(3)
  })

  test('by tag, toggling off on a second click', async ({ page }) => {
    // Tag chips render as "#tag", sorted.
    await expect(page.getByRole('button', { name: /^#/ })).toHaveText([
      '#x',
      '#y',
    ])
    const tagX = page.getByRole('button', { name: '#x', exact: true })
    await tagX.click()
    await expect(tagX).toHaveAttribute('aria-pressed', 'true')
    await expect(cardTitles(page)).toHaveCount(2)
    await expect(card(page, names.activeY)).toHaveCount(0)

    await tagX.click()
    await expect(tagX).toHaveAttribute('aria-pressed', 'false')
    await expect(cardTitles(page)).toHaveCount(3)
  })

  test('only one tag is active at a time', async ({ page }) => {
    await page.getByRole('button', { name: '#x', exact: true }).click()
    await page.getByRole('button', { name: '#y', exact: true }).click()
    await expect(
      page.getByRole('button', { name: '#x', exact: true }),
    ).toHaveAttribute('aria-pressed', 'false')
    await expect(cardTitles(page)).toHaveCount(2)
    await expect(card(page, names.inbox)).toHaveCount(0)
  })

  test('status, tag and search combine, with an empty result', async ({
    page,
  }) => {
    await statusPill(page, 'Active').click()
    await page.getByRole('button', { name: '#x', exact: true }).click()
    await expect(cardTitles(page)).toHaveText([names.activeXY])

    await page.getByPlaceholder('Search ideas, pitches, tags…').fill('nomatch')
    await expect(page.getByText('No matches')).toBeVisible()

    // "Clear filters" resets status, tag and search together.
    await page.getByRole('button', { name: 'Clear filters' }).click()
    await expect(cardTitles(page)).toHaveCount(3)
    await expect(statusPill(page, 'All')).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    await expect(
      page.getByPlaceholder('Search ideas, pitches, tags…'),
    ).toHaveValue('')
  })

  test('filters reset after visiting a project and coming back', async ({
    page,
  }) => {
    // Filter state lives in the dashboard component, so it resets when
    // the dashboard unmounts. This pins that behavior.
    await statusPill(page, 'Active').click()
    await page.getByRole('button', { name: '#y', exact: true }).click()
    await card(page, names.activeY).click()
    await page.getByRole('link', { name: 'All ideas' }).click()

    await expect(statusPill(page, 'All')).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    await expect(cardTitles(page)).toHaveCount(3)
  })

  test('filters reset after a reload', async ({ page }) => {
    await statusPill(page, 'Inbox').click()
    await expect(cardTitles(page)).toHaveCount(1)
    await page.reload()
    await expect(cardTitles(page)).toHaveCount(3)
    await expect(statusPill(page, 'All')).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  test('counts and tags update when a project changes status', async ({
    page,
  }) => {
    await card(page, names.inbox).click()
    await page.getByRole('combobox', { name: 'Status' }).selectOption('Parked')
    await page.getByRole('link', { name: 'All ideas' }).click()
    await expect(statusPill(page, 'Inbox')).toHaveText(/0$/)
    await expect(statusPill(page, 'Parked')).toHaveText(/1$/)
  })
})

// --- sort ------------------------------------------------------------------

test.describe('sort projects', () => {
  // Three projects whose order differs under every sort key:
  //            excitement  potential  effort  opportunity  target
  //   Alpha        1           1        5         -3        none
  //   Charlie      5           3        3         +5        +30d
  //   Bravo        3           4        1         +6        +10d
  // Created Alpha, Charlie, Bravo, so "Recently updated" is the reverse.
  let alpha: string, bravo: string, charlie: string
  let alphaId: string

  test.beforeEach(async ({ page, request }) => {
    const user = await registerViaApi(request)
    const id = uid()
    alpha = `Alpha ${id}`
    bravo = `Bravo ${id}`
    charlie = `Charlie ${id}`
    alphaId = (
      await createProjectViaApi(request, user, {
        name: alpha,
        excitement: 1,
        potential: 1,
        effort: 5,
      })
    ).id
    await createProjectViaApi(request, user, {
      name: charlie,
      excitement: 5,
      potential: 3,
      effort: 3,
      targetDate: isoDateFromToday(30),
    })
    await createProjectViaApi(request, user, {
      name: bravo,
      excitement: 3,
      potential: 4,
      effort: 1,
      targetDate: isoDateFromToday(10),
    })
    await signInAs(page, user)
    await openDashboard(page)
  })

  test('defaults to recently updated', async ({ page }) => {
    await expect(
      page.getByRole('combobox', { name: 'Sort projects' }),
    ).toHaveValue('updated')
    await expect(cardTitles(page)).toHaveText([bravo, charlie, alpha])
  })

  // Option values come from SORT_LABELS in components/dashboard/sort-options.ts.
  const cases: [string, () => string[]][] = [
    ['name', () => [alpha, bravo, charlie]],
    ['excitement', () => [charlie, bravo, alpha]],
    ['effort', () => [bravo, charlie, alpha]],
    ['opportunity', () => [bravo, charlie, alpha]],
    // No target date sorts last.
    ['target', () => [bravo, charlie, alpha]],
  ]
  for (const [key, expected] of cases) {
    test(`by ${key}`, async ({ page }) => {
      await page
        .getByRole('combobox', { name: 'Sort projects' })
        .selectOption(key)
      await expect(cardTitles(page)).toHaveText(expected())
    })
  }

  test('sort applies on top of filters', async ({ page }) => {
    // "r" is in Bravo and Charlie but not Alpha (the hex suffix has no r).
    await page.getByPlaceholder('Search ideas, pitches, tags…').fill('r')
    const sort = page.getByRole('combobox', { name: 'Sort projects' })
    await sort.selectOption('name')
    await expect(cardTitles(page)).toHaveText([bravo, charlie])
    await sort.selectOption('excitement')
    await expect(cardTitles(page)).toHaveText([charlie, bravo])
  })

  test('editing a project moves it to the top of "Recently updated"', async ({
    page,
  }) => {
    await card(page, alpha).click()
    const patched = waitForApi(page, 'PATCH', `/projects/${alphaId}`)
    await page.getByRole('button', { name: 'Potential 2 of 5' }).click()
    await patched
    await page.getByRole('link', { name: 'All ideas' }).click()
    await expect(cardTitles(page)).toHaveText([alpha, bravo, charlie])
  })

  test('sort resets to the default after navigating away', async ({ page }) => {
    const sort = page.getByRole('combobox', { name: 'Sort projects' })
    await sort.selectOption('name')
    await card(page, alpha).click()
    await page.getByRole('link', { name: 'All ideas' }).click()
    await expect(sort).toHaveValue('updated')
  })
})

// --- edit ------------------------------------------------------------------

test.describe('edit project', () => {
  let user: TestUser
  let original: ApiProject

  test.beforeEach(async ({ page, request }) => {
    user = await registerViaApi(request)
    original = await createProjectViaApi(request, user, {
      name: `Editable ${uid()}`,
      pitch: 'Old pitch',
      tags: ['existing'],
      targetDate: isoDateFromToday(20),
    })
    await signInAs(page, user)
  })

  /**
   * Text fields save on blur, one PATCH per field, sending only that
   * field. Wait on each PATCH before the next edit so the request-body
   * assertion lines up with the field just changed.
   */
  async function expectPatch(
    page: Page,
    action: () => Promise<unknown>,
    body: object,
  ) {
    const patched = waitForApi(page, 'PATCH', `/projects/${original.id}`)
    await action()
    const res = await patched
    expect(res.status()).toBe(200)
    expect(res.request().postDataJSON()).toEqual(body)
  }

  test('saves each edited field and persists across reload', async ({
    page,
    request,
  }) => {
    await openDashboard(page)
    await card(page, original.name).click()
    await expect(page).toHaveURL(`/project/${original.id}`)

    const nameInput = detailNameInput(page)
    await expect(nameInput).toHaveValue(original.name)
    const newName = `Renamed ${uid()}`
    await expectPatch(
      page,
      async () => {
        await nameInput.fill(newName)
        await nameInput.blur()
      },
      { name: newName },
    )

    const pitch = page.getByPlaceholder('One-line pitch: the scannable version')
    await expectPatch(
      page,
      async () => {
        await pitch.fill('New pitch')
        await pitch.blur()
      },
      { pitch: 'New pitch' },
    )

    await expectPatch(
      page,
      async () => {
        await page.locator('#description').fill('Updated description')
        await page.locator('#description').blur()
      },
      { description: 'Updated description' },
    )

    const nextAction = page.getByPlaceholder('The single next concrete step…')
    await expectPatch(
      page,
      async () => {
        await nextAction.fill('Ship it')
        await nextAction.blur()
      },
      { nextAction: 'Ship it' },
    )

    // Status, scores, date and tags save immediately on change.
    await expectPatch(
      page,
      () =>
        page.getByRole('combobox', { name: 'Status' }).selectOption('Active'),
      { status: 'Active' },
    )
    await expectPatch(
      page,
      () => page.getByRole('button', { name: 'Excitement 4 of 5' }).click(),
      { excitement: 4 },
    )
    const targetDate = isoDateFromToday(14)
    await expectPatch(
      page,
      () => page.locator('#target-date').fill(targetDate),
      { targetDate },
    )
    // Tags are lowercased before saving and appended to existing ones.
    await expectPatch(
      page,
      async () => {
        await page.getByPlaceholder('Add a tag…').fill('Edited')
        await page.getByPlaceholder('Add a tag…').press('Enter')
      },
      { tags: ['existing', 'edited'] },
    )
    await expect(
      page.getByRole('button', { name: 'Remove tag edited' }),
    ).toBeVisible()

    // Persisted server-side.
    const fetched = await getProjectViaApi(request, user, original.id)
    expect(await fetched.json()).toMatchObject({
      name: newName,
      pitch: 'New pitch',
      description: 'Updated description',
      nextAction: 'Ship it',
      status: 'Active',
      excitement: 4,
      targetDate,
      tags: ['existing', 'edited'],
    })

    // And reflected after a full reload, which re-reads from the API.
    const reloaded = waitForApi(page, 'GET', '/projects')
    await page.reload()
    await reloaded
    await expect(detailNameInput(page)).toHaveValue(newName)
    await expect(page.locator('#description')).toHaveValue(
      'Updated description',
    )
    await expect(page.getByRole('combobox', { name: 'Status' })).toHaveValue(
      'Active',
    )

    await page.getByRole('link', { name: 'All ideas' }).click()
    await expect(card(page, newName)).toContainText('New pitch')
    await expect(card(page, original.name)).toHaveCount(0)
  })

  test('unchanged fields send nothing on blur', async ({ page }) => {
    const patches = recordRequests(page, 'PATCH', `/projects/${original.id}`)
    await openProject(page, original.id)
    await detailNameInput(page).click()
    await detailNameInput(page).blur()
    await page.locator('#description').click()
    await page.locator('#description').blur()
    // Give any stray request a chance to fire.
    await page.waitForLoadState('networkidle')
    expect(patches).toHaveLength(0)
  })

  test('a blank name is not saved', async ({ page, request }) => {
    const patches = recordRequests(page, 'PATCH', `/projects/${original.id}`)
    await openProject(page, original.id)
    await detailNameInput(page).fill('   ')
    await detailNameInput(page).blur()
    await page.waitForLoadState('networkidle')
    expect(patches).toHaveLength(0)
    expect(
      (await (await getProjectViaApi(request, user, original.id)).json()).name,
    ).toBe(original.name)
    // The field isn't reset in place; a reload shows the saved name.
    await page.reload()
    await expect(detailNameInput(page)).toHaveValue(original.name)
  })

  test('name is trimmed before saving', async ({ page }) => {
    await openProject(page, original.id)
    await expectPatch(
      page,
      async () => {
        await detailNameInput(page).fill('  Padded name  ')
        await detailNameInput(page).blur()
      },
      { name: 'Padded name' },
    )
  })

  test('tags: duplicates ignored, removal saves, Add button works', async ({
    page,
  }) => {
    const patches = recordRequests(page, 'PATCH', `/projects/${original.id}`)
    await openProject(page, original.id)
    const tagInput = page.getByPlaceholder('Add a tag…')
    const addTag = page.getByRole('button', { name: 'Add tag' })

    await expect(addTag).toBeDisabled()
    // Same tag in different case: lowercased, already present, no PATCH.
    await tagInput.fill('EXISTING')
    await tagInput.press('Enter')
    await expect(tagInput).toHaveValue('')
    await page.waitForLoadState('networkidle')
    expect(patches).toHaveLength(0)

    await expectPatch(
      page,
      async () => {
        await tagInput.fill('second')
        await addTag.click()
      },
      { tags: ['existing', 'second'] },
    )
    await expectPatch(
      page,
      () => page.getByRole('button', { name: 'Remove tag existing' }).click(),
      { tags: ['second'] },
    )
    await expectPatch(
      page,
      () => page.getByRole('button', { name: 'Remove tag second' }).click(),
      { tags: [] },
    )
    await expect(page.getByText('No tags yet.')).toBeVisible()
  })

  test('links: scheme added when missing, label optional, removal saves', async ({
    page,
  }) => {
    await openProject(page, original.id)
    await expect(page.getByText('No links yet.')).toBeVisible()

    await expectPatch(
      page,
      async () => {
        await page.getByPlaceholder('https://…').fill('example.com/a')
        await page.getByRole('button', { name: 'Add link' }).click()
      },
      { links: [{ url: 'https://example.com/a' }] },
    )
    await expectPatch(
      page,
      async () => {
        await page.getByPlaceholder('Label (optional)').fill('Docs')
        await page.getByPlaceholder('https://…').fill('http://docs.test')
        await page.getByPlaceholder('https://…').press('Enter')
      },
      {
        links: [
          { url: 'https://example.com/a', label: null },
          { label: 'Docs', url: 'http://docs.test' },
        ],
      },
    )
    const docs = page.getByRole('link', { name: 'Docs' })
    await expect(docs).toHaveAttribute('href', 'http://docs.test')
    await expect(docs).toHaveAttribute('target', '_blank')

    // The remove button only shows on hover.
    await docs.hover()
    await expectPatch(
      page,
      () => page.getByRole('button', { name: 'Remove link Docs' }).click(),
      { links: [{ url: 'https://example.com/a', label: null }] },
    )
  })

  test('scores: each picker saves its own field', async ({ page }) => {
    await openProject(page, original.id)
    await expectPatch(
      page,
      () => page.getByRole('button', { name: 'Effort 1 of 5' }).click(),
      { effort: 1 },
    )
    await expectPatch(
      page,
      () => page.getByRole('button', { name: 'Potential 5 of 5' }).click(),
      { potential: 5 },
    )
    // aria-pressed marks every segment up to the value.
    for (const n of [1, 2, 3, 4, 5]) {
      await expect(
        page.getByRole('button', { name: `Potential ${n} of 5` }),
      ).toHaveAttribute('aria-pressed', 'true')
    }
    await expect(
      page.getByRole('button', { name: 'Effort 2 of 5' }),
    ).toHaveAttribute('aria-pressed', 'false')
  })

  test('target date: past dates allowed, clearing sends null', async ({
    page,
    request,
  }) => {
    await openProject(page, original.id)
    await expectPatch(
      page,
      () => page.locator('#target-date').fill('2001-02-03'),
      { targetDate: '2001-02-03' },
    )
    await expectPatch(page, () => page.locator('#target-date').fill(''), {
      targetDate: null,
    })
    expect(
      (await (await getProjectViaApi(request, user, original.id)).json())
        .targetDate,
    ).toBeNull()
  })

  test('long and unicode text persists', async ({ page, request }) => {
    await openProject(page, original.id)
    const desc = `${'Ünïcödé 日本語 🚀 '.repeat(300)}\n\nlast line`
    await expectPatch(
      page,
      async () => {
        await page.locator('#description').fill(desc)
        await page.locator('#description').blur()
      },
      { description: desc },
    )
    expect(
      (await (await getProjectViaApi(request, user, original.id)).json())
        .description,
    ).toBe(desc)
    expect(await hasHorizontalScroll(page)).toBe(false)
  })

  test('a failed save shows a toast and reverts the field', async ({
    page,
    request,
  }) => {
    await openProject(page, original.id)
    await page.route(apiRoute(`/projects/${original.id}`), (route) =>
      route.request().method() === 'PATCH'
        ? route.fulfill({ status: 500, json: { detail: 'Could not save' } })
        : route.fallback(),
    )
    await detailNameInput(page).fill('Doomed rename')
    await detailNameInput(page).blur()

    await expect(toast(page, 'Could not save')).toBeVisible()
    await expect(detailNameInput(page)).toHaveValue(original.name)
    expect(
      (await (await getProjectViaApi(request, user, original.id)).json()).name,
    ).toBe(original.name)
  })

  test('a deep link to a missing project shows "Idea not found"', async ({
    page,
  }) => {
    await page.goto(`/project/${crypto.randomUUID()}`)
    await expect(page.getByText('Idea not found')).toBeVisible()
    await page.getByRole('link', { name: 'Back to dashboard' }).click()
    await expect(page.getByRole('heading', { name: 'Ideas' })).toBeVisible()
  })
})

// --- notes -----------------------------------------------------------------

test.describe('notes', () => {
  let user: TestUser
  let project: ApiProject

  test.beforeEach(async ({ page, request }) => {
    user = await registerViaApi(request)
    project = await createProjectViaApi(request, user, {
      name: `Notes ${uid()}`,
    })
    await signInAs(page, user)
  })

  const noteBox = (page: Page) =>
    page.getByPlaceholder('Add a note, thought, or update…')
  const notesPath = () => `/projects/${project.id}/notes`
  const noteItems = (page: Page) => page.locator('main ul li p')

  test('starts empty, then adds notes newest first', async ({
    page,
    request,
  }) => {
    await openProject(page, project.id)
    await expect(page.getByText('No notes yet.')).toBeVisible()

    for (const text of ['First note', 'Second note']) {
      await noteBox(page).fill(text)
      const added = waitForApi(page, 'POST', notesPath())
      await page.getByRole('button', { name: 'Add note' }).click()
      const res = await added
      expect(res.status()).toBe(201)
      expect(res.request().postDataJSON()).toEqual({ body: text })
      await expect(noteBox(page)).toHaveValue('')
    }

    await expect(noteItems(page)).toHaveText(['Second note', 'First note'])
    expect(
      (await listNotesViaApi(request, user, project.id)).map((n) => n.body),
    ).toEqual(['Second note', 'First note'])
  })

  test('shows existing notes from the API', async ({ page, request }) => {
    await addNoteViaApi(request, user, project.id, 'older')
    await addNoteViaApi(request, user, project.id, 'newer')
    await openProject(page, project.id)
    await expect(noteItems(page)).toHaveText(['newer', 'older'])
  })

  test('Ctrl/Cmd+Enter adds; text is trimmed; line breaks kept', async ({
    page,
    request,
  }) => {
    await openProject(page, project.id)
    await noteBox(page).fill('  line one\nline two  ')
    const added = waitForApi(page, 'POST', notesPath())
    await noteBox(page).press('ControlOrMeta+Enter')
    expect((await added).request().postDataJSON()).toEqual({
      body: 'line one\nline two',
    })
    // whitespace-pre-wrap keeps the newline visible.
    await expect(noteItems(page).first()).toHaveText('line one\nline two')
    expect((await listNotesViaApi(request, user, project.id))[0].body).toBe(
      'line one\nline two',
    )
  })

  test('Add is disabled for empty or whitespace notes', async ({ page }) => {
    const posts = recordRequests(page, 'POST', notesPath())
    await openProject(page, project.id)
    const add = page.getByRole('button', { name: 'Add note' })
    await expect(add).toBeDisabled()
    await noteBox(page).fill('   \n  ')
    await expect(add).toBeDisabled()
    await noteBox(page).press('ControlOrMeta+Enter')
    await page.waitForLoadState('networkidle')
    expect(posts).toHaveLength(0)
  })

  test('Add is disabled while saving', async ({ page }) => {
    await openProject(page, project.id)
    const { release, held } = await holdRequests(page, notesPath(), 'POST')
    await noteBox(page).fill('Slow note')
    const add = page.getByRole('button', { name: 'Add note' })
    await add.click()
    await held
    await expect(add).toBeDisabled()
    release()
    await expect(noteItems(page)).toHaveText(['Slow note'])
  })

  test('long and unicode notes', async ({ page, request }) => {
    await openProject(page, project.id)
    const text = `${'Ünïcödé 日本語 🚀 '.repeat(500)}end`
    await noteBox(page).fill(text)
    const added = waitForApi(page, 'POST', notesPath())
    await page.getByRole('button', { name: 'Add note' }).click()
    await added
    await expect(noteItems(page).first()).toHaveText(text)
    expect((await listNotesViaApi(request, user, project.id))[0].body).toBe(
      text,
    )
    expect(await hasHorizontalScroll(page)).toBe(false)
  })

  test('deleting asks for confirmation; Cancel keeps the note', async ({
    page,
    request,
  }) => {
    const keep = await addNoteViaApi(request, user, project.id, 'Keep me')
    const drop = await addNoteViaApi(request, user, project.id, 'Delete me')
    await openProject(page, project.id)

    const dropItem = page.locator('main ul li').filter({ hasText: 'Delete me' })
    await dropItem.hover()
    await dropItem.getByRole('button', { name: 'Delete note' }).click()
    await expect(dropItem.getByText('Delete this note?')).toBeVisible()
    await dropItem.getByRole('button', { name: 'Cancel' }).click()
    await expect(dropItem.getByText('Delete this note?')).toBeHidden()

    await dropItem.hover()
    await dropItem.getByRole('button', { name: 'Delete note' }).click()
    const deleted = waitForApi(page, 'DELETE', `/notes/${drop.id}`)
    await dropItem.getByRole('button', { name: 'Delete', exact: true }).click()
    expect((await deleted).status()).toBe(200)

    await expect(noteItems(page)).toHaveText(['Keep me'])
    expect(
      (await listNotesViaApi(request, user, project.id)).map((n) => n.id),
    ).toEqual([keep.id])
  })

  test('a failed delete keeps the note and shows a toast', async ({
    page,
    request,
  }) => {
    const note = await addNoteViaApi(request, user, project.id, 'Sticky')
    await openProject(page, project.id)
    await page.route(apiRoute(`/notes/${note.id}`), (route) =>
      route.fulfill({ status: 500, json: { detail: 'Delete failed' } }),
    )
    const item = page.locator('main ul li').filter({ hasText: 'Sticky' })
    await item.hover()
    await item.getByRole('button', { name: 'Delete note' }).click()
    await item.getByRole('button', { name: 'Delete', exact: true }).click()

    await expect(toast(page, 'Delete failed')).toBeVisible()
    await expect(noteItems(page)).toHaveText(['Sticky'])
  })

  test('cannot add a note to a project deleted elsewhere', async ({
    page,
    request,
  }) => {
    await openProject(page, project.id)
    // Deleted behind this page's back (another tab, another device).
    await request.delete(`${API_URL}/projects/${project.id}`, {
      headers: bearer(user.token),
    })

    await noteBox(page).fill('Too late')
    const added = waitForApi(page, 'POST', notesPath())
    await page.getByRole('button', { name: 'Add note' }).click()
    expect((await added).status()).toBe(404)

    await expect(toast(page, 'Project not found')).toBeVisible()
    // The draft survives the failure.
    await expect(noteBox(page)).toHaveValue('Too late')
  })
})

// --- delete ----------------------------------------------------------------

test.describe('delete project', () => {
  let user: TestUser
  let doomed: ApiProject
  let kept: ApiProject

  test.beforeEach(async ({ page, request }) => {
    user = await registerViaApi(request)
    const id = uid()
    doomed = await createProjectViaApi(request, user, { name: `Doomed ${id}` })
    kept = await createProjectViaApi(request, user, { name: `Kept ${id}` })
    await addNoteViaApi(request, user, doomed.id, 'goes with it')
    await signInAs(page, user)
  })

  test('confirms, deletes, and removes the card', async ({ page, request }) => {
    await openDashboard(page)
    await expect(cardTitles(page)).toHaveCount(2)

    await card(page, doomed.name).click()
    await expect(page).toHaveURL(`/project/${doomed.id}`)

    // The trash icon only arms a confirm step; Cancel backs out of it.
    await page.getByRole('button', { name: 'Delete idea' }).click()
    await expect(page.getByText('Delete this idea?')).toBeVisible()
    await page.getByRole('button', { name: 'Cancel' }).click()
    await expect(page.getByText('Delete this idea?')).toBeHidden()

    await page.getByRole('button', { name: 'Delete idea' }).click()
    const deleted = waitForApi(page, 'DELETE', `/projects/${doomed.id}`)
    await page.getByRole('button', { name: 'Delete', exact: true }).click()
    expect((await deleted).status()).toBe(204)

    await expect(page).toHaveURL('/')
    await expect(cardTitles(page)).toHaveText([kept.name])
    await expect(statusPill(page, 'All')).toHaveText(/1$/)

    expect((await getProjectViaApi(request, user, doomed.id)).status()).toBe(
      404,
    )
    // Its notes went with it.
    const notes = await request.get(`${API_URL}/projects/${doomed.id}/notes`, {
      headers: bearer(user.token),
    })
    expect(notes.status()).toBe(404)
  })

  test('a failed delete stays on the page with a toast', async ({
    page,
    request,
  }) => {
    await openProject(page, doomed.id)
    await page.route(apiRoute(`/projects/${doomed.id}`), (route) =>
      route.request().method() === 'DELETE'
        ? route.fulfill({ status: 500, json: { detail: 'Delete blocked' } })
        : route.fallback(),
    )
    await page.getByRole('button', { name: 'Delete idea' }).click()
    await page.getByRole('button', { name: 'Delete', exact: true }).click()

    await expect(toast(page, 'Delete blocked')).toBeVisible()
    await expect(page).toHaveURL(`/project/${doomed.id}`)
    // Back to the unarmed state so a retry starts clean.
    await expect(
      page.getByRole('button', { name: 'Delete idea' }),
    ).toBeVisible()
    expect((await getProjectViaApi(request, user, doomed.id)).status()).toBe(
      200,
    )
  })

  test('the deleted project’s URL shows "Idea not found"', async ({ page }) => {
    await openProject(page, doomed.id)
    await page.getByRole('button', { name: 'Delete idea' }).click()
    await page.getByRole('button', { name: 'Delete', exact: true }).click()
    await expect(page).toHaveURL('/')

    await page.goBack()
    await expect(page.getByText('Idea not found')).toBeVisible()
  })
})

// --- multiple tabs ---------------------------------------------------------

test.describe('multiple tabs', () => {
  test('edits from two tabs merge field-by-field; stale tab catches up on reload', async ({
    page,
    request,
  }) => {
    const user = await registerViaApi(request)
    const project = await createProjectViaApi(request, user, {
      name: `Shared ${uid()}`,
      pitch: 'Shared pitch',
    })
    // signInAs() sets the cookie on the whole context, so the second tab
    // is signed in too (they share cookies, like real tabs).
    await signInAs(page, user)
    const tabA = page
    const tabB = await page.context().newPage()
    await openProject(tabA, project.id)
    await openProject(tabB, project.id)

    // A renames.
    const renamed = `Renamed in A ${uid()}`
    const patchA = waitForApi(tabA, 'PATCH', `/projects/${project.id}`)
    await detailNameInput(tabA).fill(renamed)
    await detailNameInput(tabA).blur()
    await patchA

    // B has no live sync: it still shows the old name.
    await expect(detailNameInput(tabB)).toHaveValue(project.name)

    // B edits a different field. PATCH sends only that field, so A's
    // rename is not clobbered by B's stale copy.
    const patchB = waitForApi(tabB, 'PATCH', `/projects/${project.id}`)
    await tabB
      .getByPlaceholder('One-line pitch: the scannable version')
      .fill('Pitch from B')
    await tabB.getByPlaceholder('One-line pitch: the scannable version').blur()
    expect((await patchB).request().postDataJSON()).toEqual({
      pitch: 'Pitch from B',
    })

    expect(
      await (await getProjectViaApi(request, user, project.id)).json(),
    ).toMatchObject({ name: renamed, pitch: 'Pitch from B' })

    await tabB.reload()
    await expect(detailNameInput(tabB)).toHaveValue(renamed)
    await tabA.reload()
    await expect(
      tabA.getByPlaceholder('One-line pitch: the scannable version'),
    ).toHaveValue('Pitch from B')
  })

  test('same field edited in two tabs: last write wins', async ({
    page,
    request,
  }) => {
    const user = await registerViaApi(request)
    const project = await createProjectViaApi(request, user, {
      name: `Race ${uid()}`,
    })
    await signInAs(page, user)
    const tabB = await page.context().newPage()
    await openProject(page, project.id)
    await openProject(tabB, project.id)

    for (const [tab, value] of [
      [page, 'From A'],
      [tabB, 'From B'],
    ] as const) {
      const patched = waitForApi(tab, 'PATCH', `/projects/${project.id}`)
      await tab.locator('#description').fill(value)
      await tab.locator('#description').blur()
      await patched
    }
    expect(
      (await (await getProjectViaApi(request, user, project.id)).json())
        .description,
    ).toBe('From B')
  })

  test('a project deleted in one tab can’t be edited in the other', async ({
    page,
    request,
  }) => {
    const user = await registerViaApi(request)
    const project = await createProjectViaApi(request, user, {
      name: `Ghost ${uid()}`,
    })
    await signInAs(page, user)
    const tabB = await page.context().newPage()
    await openProject(page, project.id)
    await openProject(tabB, project.id)

    await page.getByRole('button', { name: 'Delete idea' }).click()
    await page.getByRole('button', { name: 'Delete', exact: true }).click()
    await expect(page).toHaveURL('/')

    // Tab B still shows the project; its edits now 404.
    const patched = waitForApi(tabB, 'PATCH', `/projects/${project.id}`)
    await tabB.getByRole('combobox', { name: 'Status' }).selectOption('Active')
    expect((await patched).status()).toBe(404)
    await expect(toast(tabB, 'Project not found')).toBeVisible()

    // Signing out in one tab doesn't push the other to login until it
    // next talks to the API or reloads.
  })
})

// --- rapid sequences -------------------------------------------------------

test.describe('rapid sequences', () => {
  test('several quick captures in a row all land', async ({
    page,
    request,
  }) => {
    const user = await registerViaApi(request)
    await signInAs(page, user)
    await openDashboard(page)

    const id = uid()
    const names = Array.from({ length: 5 }, (_, i) => `Rapid ${i} ${id}`)
    for (const name of names) {
      await headerCapture(page).click()
      await captureDialog(page).locator('#qc-name').fill(name)
      await captureDialog(page).locator('#qc-name').press('Enter')
      // Don't wait for the response: the next open waits for the dialog
      // to close, which only happens once the create has succeeded.
      await expect(captureDialog(page)).toBeHidden()
    }

    await expect(cardTitles(page)).toHaveCount(5)
    const res = await request.get(`${API_URL}/projects`, {
      headers: bearer(user.token),
    })
    expect(
      ((await res.json()) as ApiProject[]).map((p) => p.name).sort(),
    ).toEqual([...names].sort())
  })

  test('create, edit and delete back-to-back', async ({ page, request }) => {
    const user = await registerViaApi(request)
    await signInAs(page, user)
    await openDashboard(page)

    const a = await quickCapture(page, `Quick A ${uid()}`)
    const b = await quickCapture(page, `Quick B ${uid()}`)

    // Edit A: status and score without waiting between clicks.
    await card(page, a.name).click()
    const patches = waitForApi(page, 'PATCH', `/projects/${a.id}`)
    await page.getByRole('combobox', { name: 'Status' }).selectOption('Active')
    await page.getByRole('button', { name: 'Excitement 5 of 5' }).click()
    await patches
    await expect(
      page.getByRole('button', { name: 'Excitement 5 of 5' }),
    ).toHaveAttribute('aria-pressed', 'true')

    // Delete B straight away.
    await page.getByRole('link', { name: 'All ideas' }).click()
    await card(page, b.name).click()
    await page.getByRole('button', { name: 'Delete idea' }).click()
    const deleted = waitForApi(page, 'DELETE', `/projects/${b.id}`)
    await page.getByRole('button', { name: 'Delete', exact: true }).click()
    await deleted

    await expect(cardTitles(page)).toHaveText([a.name])
    // Wait for both PATCHes to have landed server-side.
    await expect
      .poll(async () => (await getProjectViaApi(request, user, a.id)).json())
      .toMatchObject({ status: 'Active', excitement: 5 })
    expect((await getProjectViaApi(request, user, b.id)).status()).toBe(404)
  })

  test('double-clicking Capture creates one project', async ({
    page,
    request,
  }) => {
    const user = await registerViaApi(request)
    await signInAs(page, user)
    await openDashboard(page)
    const posts = recordRequests(page, 'POST', '/projects')

    await headerCapture(page).click()
    const name = `Double ${uid()}`
    await captureDialog(page).locator('#qc-name').fill(name)
    await captureDialog(page)
      .getByRole('button', { name: 'Capture', exact: true })
      .dblclick()
    await expect(captureDialog(page)).toBeHidden()
    await page.waitForLoadState('networkidle')

    expect(posts).toHaveLength(1)
    const res = await request.get(`${API_URL}/projects`, {
      headers: bearer(user.token),
    })
    expect(await res.json()).toHaveLength(1)
  })
})

// --- responsive ------------------------------------------------------------

test.describe('responsive: phone (375×812)', () => {
  test.use({ viewport: { width: 375, height: 812 } })

  test('signup works and the dashboard fits the screen', async ({ page }) => {
    await goToSignup(page)
    expect(await hasHorizontalScroll(page)).toBe(false)
    await page.locator('#signup-email').fill(uniqueEmail())
    await page.locator('#signup-password').fill(PASSWORD)
    await page.getByRole('button', { name: 'Sign up' }).click()
    await expect(page.getByRole('heading', { name: 'Ideas' })).toBeVisible()
    expect(await hasHorizontalScroll(page)).toBe(false)
  })

  test('header collapses: short Capture label, no user label', async ({
    page,
    request,
  }) => {
    const user = await registerViaApi(request)
    await signInAs(page, user)
    await openDashboard(page)
    const banner = page.getByRole('banner')
    await expect(
      banner.getByRole('button', { name: 'Capture', exact: true }),
    ).toBeVisible()
    await expect(banner.getByText('Quick capture')).toBeHidden()
    await expect(banner.getByText(user.email)).toBeHidden()
    await expect(banner.getByRole('button', { name: 'Sign out' })).toBeVisible()
  })

  test('quick capture fits the screen and saves', async ({ page, request }) => {
    const user = await registerViaApi(request)
    await signInAs(page, user)
    await openDashboard(page)

    await page
      .getByRole('banner')
      .getByRole('button', { name: 'Capture', exact: true })
      .click()
    const dialog = captureDialog(page)
    await expect(dialog).toBeVisible()
    const box = await dialog.boundingBox()
    expect(box!.width).toBeLessThanOrEqual(375)
    expect(box!.x).toBeGreaterThanOrEqual(0)

    const name = `Phone ${uid()}`
    await dialog.locator('#qc-name').fill(name)
    await dialog.getByRole('button', { name: 'Capture', exact: true }).click()
    await expect(card(page, name)).toBeVisible()
  })

  test('project detail fits the screen', async ({ page, request }) => {
    const user = await registerViaApi(request)
    const project = await createProjectViaApi(request, user, {
      name: `Phone detail ${uid()}`,
      tags: ['one', 'two', 'three'],
      links: [{ label: 'A long link label here', url: 'https://example.com' }],
    })
    await addNoteViaApi(request, user, project.id, 'A note on a phone')
    await signInAs(page, user)
    await openProject(page, project.id)
    await expect(detailNameInput(page)).toHaveValue(project.name)
    expect(await hasHorizontalScroll(page)).toBe(false)
  })
})

test.describe('responsive: tablet (768×1024)', () => {
  test.use({ viewport: { width: 768, height: 1024 } })

  test('full header and no horizontal scroll', async ({ page, request }) => {
    const user = await registerViaApi(request)
    for (let i = 0; i < 4; i++) {
      await createProjectViaApi(request, user, { name: `Tab ${i} ${uid()}` })
    }
    await signInAs(page, user)
    await openDashboard(page)
    await expect(headerCapture(page)).toBeVisible()
    await expect(page.getByRole('banner').getByText(user.email)).toBeVisible()
    await expect(cardTitles(page)).toHaveCount(4)
    expect(await hasHorizontalScroll(page)).toBe(false)
  })
})

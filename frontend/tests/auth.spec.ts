import {
  test,
  expect,
  type APIRequestContext,
  type Page,
  type Response,
} from '@playwright/test'

// The frontend talks to uvicorn directly in local dev (frontend/.env sets
// VITE_API_BASE_URL=http://localhost:8000). Locally the routers have no
// /api prefix; that only exists behind CloudFront.
const API_URL = process.env.E2E_API_URL ?? 'http://localhost:8000'
const PASSWORD = 'e2e-password-123'

// --- helpers ---------------------------------------------------------------

/** Unique per call, so parallel workers never collide on emails or names. */
function uid(): string {
  return crypto.randomUUID().slice(0, 8)
}

/** A YYYY-MM-DD date `days` from today, in local time like the app uses. */
function isoDateFromToday(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}

/**
 * Wait for one backend call. Match on method + exact pathname, since
 * response URLs are absolute (http://localhost:8000/...) and endsWith
 * would also match e.g. /projects/:id/notes for "/projects".
 */
function waitForApi(
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

interface TestUser {
  email: string
  token: string
}

/** Register straight against the API; faster than the UI for setup. */
async function registerViaApi(
  request: APIRequestContext,
  displayName?: string,
): Promise<TestUser> {
  const email = `e2e-${crypto.randomUUID()}@example.com`
  const res = await request.post(`${API_URL}/auth/register`, {
    data: { email, password: PASSWORD, displayName },
  })
  expect(res.status()).toBe(201)
  const { access_token } = (await res.json()) as { access_token: string }
  return { email, token: access_token }
}

interface ProjectSeed {
  name: string
  pitch?: string
  status?: string
  tags?: string[]
  excitement?: number
  effort?: number
  potential?: number
  targetDate?: string | null
}

interface ApiProject extends Required<Omit<ProjectSeed, 'targetDate'>> {
  id: string
  description: string
  nextAction: string
  targetDate: string | null
}

async function createProjectViaApi(
  request: APIRequestContext,
  user: TestUser,
  seed: ProjectSeed,
): Promise<ApiProject> {
  const res = await request.post(`${API_URL}/projects`, {
    headers: { Authorization: `Bearer ${user.token}` },
    data: seed,
  })
  expect(res.status()).toBe(201)
  return (await res.json()) as ApiProject
}

async function getProjectViaApi(
  request: APIRequestContext,
  user: TestUser,
  id: string,
) {
  return request.get(`${API_URL}/projects/${id}`, {
    headers: { Authorization: `Bearer ${user.token}` },
  })
}

/**
 * Sign the browser in without going through the login form: the app
 * reads its bearer token from localStorage['hub.token'] on boot. An init
 * script runs before any page script on every navigation, so the token is
 * in place before AuthProvider checks for it.
 */
async function signInAs(page: Page, user: TestUser): Promise<void> {
  await page.addInitScript((token) => {
    localStorage.setItem('hub.token', token)
  }, user.token)
}

/**
 * Open the dashboard and wait until the store's initial GET /projects has
 * landed. Until then the dashboard shows skeleton cards, so asserting on
 * card contents earlier would race the fetch.
 */
async function openDashboard(page: Page): Promise<void> {
  const loaded = waitForApi(page, 'GET', '/projects')
  await page.goto('/')
  expect((await loaded).status()).toBe(200)
  await expect(page.getByRole('heading', { name: 'Ideas' })).toBeVisible()
}

/** Project cards are links to /project/:id with the name in an <h3>. */
function cardTitles(page: Page) {
  return page.locator('main a[href^="/project/"] h3')
}

function card(page: Page, name: string) {
  return page.locator('main a[href^="/project/"]').filter({
    has: page.getByRole('heading', { name, exact: true }),
  })
}

/**
 * Status filter pills render "<Status><count>" as two text nodes, so the
 * accessible name is e.g. "Active 2" (or "Active2"). Match on the prefix.
 */
function statusPill(page: Page, label: string) {
  return page.getByRole('button', { name: new RegExp(`^${label}\\s*\\d+$`) })
}

// --- auth ------------------------------------------------------------------

test.describe('auth', () => {
  test('signs up a new user and lands on the dashboard', async ({ page }) => {
    const email = `e2e-${crypto.randomUUID()}@example.com`
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
    expect((await registered).status()).toBe(201)

    // The dashboard is the authenticated "/" route.
    await expect(page).toHaveURL('/')
    await expect(page.getByRole('heading', { name: 'Ideas' })).toBeVisible()
    await expect(page.getByText(displayName)).toBeVisible()
    await expect(page.getByText('Nothing captured yet')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
  })

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
  })

  test('signs out back to the login page', async ({ page, request }) => {
    const user = await registerViaApi(request)

    // Not signInAs(): its init script would re-insert the token on the
    // next navigation and undo the sign-out. Log in through the form.
    await page.goto('/login')
    await page.locator('#login-email').fill(user.email)
    await page.locator('#login-password').fill(PASSWORD)
    await page.getByRole('button', { name: 'Log in' }).click()
    await expect(page.getByRole('heading', { name: 'Ideas' })).toBeVisible()

    await page.getByRole('button', { name: 'Sign out' }).click()

    await expect(page.locator('#login-email')).toBeVisible()
    expect(
      await page.evaluate(() => localStorage.getItem('hub.token')),
    ).toBeNull()
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
    await signInAs(page, user)

    const loaded = waitForApi(page, 'GET', '/projects')
    await page.goto('/')
    const listed = (await (await loaded).json()) as ApiProject[]
    expect(listed.map((p) => p.id).sort()).toEqual([first.id, second.id].sort())

    await expect(cardTitles(page)).toHaveCount(2)
    const firstCard = card(page, first.name)
    await expect(firstCard).toContainText('First pitch')
    await expect(firstCard).toContainText('alpha')
    await expect(firstCard).toHaveAttribute('href', `/project/${first.id}`)
    // No pitch or description falls back to placeholder copy.
    await expect(card(page, second.name)).toContainText('No pitch yet.')

    await expect(statusPill(page, 'All')).toHaveText(/2$/)
    await expect(statusPill(page, 'Inbox')).toHaveText(/1$/)
    await expect(statusPill(page, 'Active')).toHaveText(/1$/)
  })
})

// --- create ----------------------------------------------------------------

test.describe('create project', () => {
  test('captures a project with full details', async ({ page, request }) => {
    const user = await registerViaApi(request)
    await signInAs(page, user)
    await openDashboard(page)

    // For a new user the empty state has its own "Quick capture" button,
    // so scope to the header to get exactly one.
    await page
      .getByRole('banner')
      .getByRole('button', { name: 'Quick capture' })
      .click()

    // base-ui keeps the dialog mounted; scope every query to it.
    const dialog = page.getByRole('dialog', { name: 'Quick capture' })
    await expect(dialog).toBeVisible()

    const name = `Captured ${uid()}`
    await dialog.locator('#qc-name').fill(name)
    await dialog.locator('#qc-pitch').fill('A pitch from E2E')

    // Status, tags, next action and scores live behind "More details".
    await dialog.getByRole('button', { name: 'More details' }).click()
    await dialog.locator('#qc-desc').fill('Brain dump text')
    await dialog.locator('#qc-status').selectOption('Exploring')
    // Tags are comma-separated, trimmed and lowercased on submit.
    await dialog.locator('#qc-tags').fill('E2E, Alpha ')
    await dialog.locator('#qc-next').fill('Write the first test')
    await dialog.getByRole('button', { name: 'Excitement 5 of 5' }).click()
    await dialog.getByRole('button', { name: 'Effort 2 of 5' }).click()

    const created = waitForApi(page, 'POST', '/projects')
    // exact: the footer also has "Capture & open".
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
    request,
  }) => {
    const user = await registerViaApi(request)
    await signInAs(page, user)
    await openDashboard(page)

    await page
      .getByRole('banner')
      .getByRole('button', { name: 'Quick capture' })
      .click()
    const dialog = page.getByRole('dialog', { name: 'Quick capture' })
    const name = `Opened ${uid()}`
    await dialog.locator('#qc-name').fill(name)

    const created = waitForApi(page, 'POST', '/projects')
    await dialog.getByRole('button', { name: 'Capture & open' }).click()
    const project = (await (await created).json()) as ApiProject

    await expect(page).toHaveURL(`/project/${project.id}`)
    // The detail page's name field is an unlabeled <input>; it's the first
    // input in <main> (next action above it is a <textarea>).
    await expect(page.locator('main input').first()).toHaveValue(name)
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

    await statusPill(page, 'All').click()
    await expect(cardTitles(page)).toHaveCount(3)
  })

  test('by tag, toggling off on a second click', async ({ page }) => {
    // Tag chips render as "#tag".
    const tagX = page.getByRole('button', { name: '#x', exact: true })
    await tagX.click()
    await expect(tagX).toHaveAttribute('aria-pressed', 'true')
    await expect(cardTitles(page)).toHaveCount(2)
    await expect(card(page, names.activeY)).toHaveCount(0)

    await tagX.click()
    await expect(tagX).toHaveAttribute('aria-pressed', 'false')
    await expect(cardTitles(page)).toHaveCount(3)
  })

  test('by status and tag combined, with an empty result', async ({ page }) => {
    await statusPill(page, 'Active').click()
    await page.getByRole('button', { name: '#x', exact: true }).click()
    await expect(cardTitles(page)).toHaveText([names.activeXY])

    // Inbox + #y matches nothing.
    await statusPill(page, 'Inbox').click()
    await page.getByRole('button', { name: '#y', exact: true }).click()
    await expect(page.getByText('No matches')).toBeVisible()

    await page.getByRole('button', { name: 'Clear filters' }).click()
    await expect(cardTitles(page)).toHaveCount(3)
    await expect(statusPill(page, 'All')).toHaveAttribute(
      'aria-pressed',
      'true',
    )
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

  test.beforeEach(async ({ page, request }) => {
    const user = await registerViaApi(request)
    const id = uid()
    alpha = `Alpha ${id}`
    bravo = `Bravo ${id}`
    charlie = `Charlie ${id}`
    await createProjectViaApi(request, user, {
      name: alpha,
      excitement: 1,
      potential: 1,
      effort: 5,
    })
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
})

// --- edit ------------------------------------------------------------------

test.describe('edit project', () => {
  test('saves each edited field and persists across reload', async ({
    page,
    request,
  }) => {
    const user = await registerViaApi(request)
    const original = await createProjectViaApi(request, user, {
      name: `Editable ${uid()}`,
      pitch: 'Old pitch',
    })
    await signInAs(page, user)
    await openDashboard(page)

    await card(page, original.name).click()
    await expect(page).toHaveURL(`/project/${original.id}`)

    const patchPath = `/projects/${original.id}`
    // Text fields save on blur, one PATCH per field, sending only that
    // field. Wait on each PATCH before the next edit so the assertions on
    // request bodies line up with the field just changed.
    async function expectPatch(action: () => Promise<void>, body: object) {
      const patched = waitForApi(page, 'PATCH', patchPath)
      await action()
      const res = await patched
      expect(res.status()).toBe(200)
      expect(res.request().postDataJSON()).toEqual(body)
    }

    // The name field has no id or label (see "Capture & open" above).
    const nameInput = page.locator('main input').first()
    await expect(nameInput).toHaveValue(original.name)
    const newName = `Renamed ${uid()}`
    await expectPatch(
      async () => {
        await nameInput.fill(newName)
        await nameInput.blur()
      },
      { name: newName },
    )

    const pitch = page.getByPlaceholder('One-line pitch: the scannable version')
    await expectPatch(
      async () => {
        await pitch.fill('New pitch')
        await pitch.blur()
      },
      { pitch: 'New pitch' },
    )

    await expectPatch(
      async () => {
        await page.locator('#description').fill('Updated description')
        await page.locator('#description').blur()
      },
      { description: 'Updated description' },
    )

    const nextAction = page.getByPlaceholder('The single next concrete step…')
    await expectPatch(
      async () => {
        await nextAction.fill('Ship it')
        await nextAction.blur()
      },
      { nextAction: 'Ship it' },
    )

    // Status, scores, date and tags save immediately on change.
    await expectPatch(
      () =>
        page
          .getByRole('combobox', { name: 'Status' })
          .selectOption('Active')
          .then(() => undefined),
      { status: 'Active' },
    )
    await expectPatch(
      () => page.getByRole('button', { name: 'Excitement 4 of 5' }).click(),
      { excitement: 4 },
    )
    const targetDate = isoDateFromToday(14)
    await expectPatch(() => page.locator('#target-date').fill(targetDate), {
      targetDate,
    })
    // Tags are lowercased before saving.
    await expectPatch(
      async () => {
        await page.getByPlaceholder('Add a tag…').fill('Edited')
        await page.getByPlaceholder('Add a tag…').press('Enter')
      },
      { tags: ['edited'] },
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
      tags: ['edited'],
    })

    // And reflected after a full reload, which re-reads from the API.
    const reloaded = waitForApi(page, 'GET', '/projects')
    await page.reload()
    await reloaded
    await expect(page.locator('main input').first()).toHaveValue(newName)
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
})

// --- delete ----------------------------------------------------------------

test.describe('delete project', () => {
  test('confirms, deletes, and removes the card', async ({ page, request }) => {
    const user = await registerViaApi(request)
    const id = uid()
    const doomed = await createProjectViaApi(request, user, {
      name: `Doomed ${id}`,
    })
    const kept = await createProjectViaApi(request, user, {
      name: `Kept ${id}`,
    })
    await signInAs(page, user)
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

    const gone = await getProjectViaApi(request, user, doomed.id)
    expect(gone.status()).toBe(404)
  })
})

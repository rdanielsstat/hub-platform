import { test, expect, type APIRequestContext } from '@playwright/test'
import {
  API_URL,
  PASSWORD,
  addNoteViaApi,
  bearer,
  canForgeTokens,
  createProjectViaApi,
  forgeToken,
  getProjectViaApi,
  isoDateFromToday,
  listNotesViaApi,
  registerViaApi,
  uid,
  uniqueEmail,
  type ApiNote,
  type ApiProject,
  type TestUser,
} from './helpers'

/**
 * Live API tests against the running FastAPI server (localhost:8000),
 * using only Playwright's request fixture; no browser. Every test makes
 * its own user(s), so tests are isolated and run in parallel.
 */

const url = (path: string) => `${API_URL}${path}`

function register(request: APIRequestContext, data: Record<string, unknown>) {
  return request.post(url('/auth/register'), { data })
}

function login(request: APIRequestContext, username: string, password: string) {
  // OAuth2 password flow: form-encoded username/password, not JSON.
  return request.post(url('/auth/login'), { form: { username, password } })
}

/** FastAPI 422 bodies list one entry per failing field. */
async function expect422(
  res: Awaited<ReturnType<APIRequestContext['get']>>,
  loc: (string | number)[],
) {
  expect(res.status()).toBe(422)
  const { detail } = (await res.json()) as {
    detail: { loc: (string | number)[] }[]
  }
  expect(detail.map((d) => d.loc)).toContainEqual(loc)
}

const ISO_DATETIME =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/

// --- health ----------------------------------------------------------------

test.describe('GET /health', () => {
  test('is public and reports ok', async ({ request }) => {
    const res = await request.get(url('/health'))
    expect(res.status()).toBe(200)
    expect(await res.json()).toEqual({ status: 'ok' })
  })
})

// --- POST /auth/register ---------------------------------------------------

test.describe('POST /auth/register', () => {
  test('creates a user and returns a bearer token', async ({ request }) => {
    const res = await register(request, {
      email: uniqueEmail(),
      password: PASSWORD,
    })
    expect(res.status()).toBe(201)
    const body = await res.json()
    expect(body).toEqual({
      access_token: expect.any(String),
      token_type: 'bearer',
    })
    // A JWT: three base64url segments.
    expect(body.access_token).toMatch(/^[\w-]+\.[\w-]+\.[\w-]+$/)
  })

  test('409 when the email is already registered', async ({ request }) => {
    const email = uniqueEmail()
    expect(
      (await register(request, { email, password: PASSWORD })).status(),
    ).toBe(201)
    const again = await register(request, { email, password: 'other-pass-123' })
    expect(again.status()).toBe(409)
    expect(await again.json()).toEqual({ detail: 'Email already registered' })
  })

  test('emails are case-insensitive: stored lowercased, duplicates by case 409', async ({
    request,
  }) => {
    const local = `Mixed-${uid()}`
    const res = await register(request, {
      email: `${local}@Example.COM`,
      password: PASSWORD,
    })
    expect(res.status()).toBe(201)
    const { access_token } = await res.json()
    const me = await request.get(url('/auth/me'), {
      headers: bearer(access_token),
    })
    expect((await me.json()).email).toBe(`${local.toLowerCase()}@example.com`)

    const dup = await register(request, {
      email: `${local.toLowerCase()}@example.com`,
      password: PASSWORD,
    })
    expect(dup.status()).toBe(409)
    // And login works with any casing.
    expect(
      (
        await login(request, `${local.toUpperCase()}@EXAMPLE.COM`, PASSWORD)
      ).status(),
    ).toBe(200)
  })

  test('surrounding whitespace in the email is stripped', async ({
    request,
  }) => {
    const email = uniqueEmail()
    const res = await register(request, {
      email: `  ${email}  `,
      password: PASSWORD,
    })
    expect(res.status()).toBe(201)
    const me = await request.get(url('/auth/me'), {
      headers: bearer((await res.json()).access_token),
    })
    expect((await me.json()).email).toBe(email)
  })

  test('accepts a long but valid email (64-char local part)', async ({
    request,
  }) => {
    const email = `${'a'.repeat(64)}@${uid()}.example.com`
    const res = await register(request, { email, password: PASSWORD })
    expect(res.status()).toBe(201)
  })

  for (const bad of [
    'not-an-email',
    'missing-at.example.com',
    '@example.com',
    'a@',
    'has space@example.com',
    '',
  ]) {
    test(`422 for invalid email ${JSON.stringify(bad)}`, async ({
      request,
    }) => {
      await expect422(
        await register(request, { email: bad, password: PASSWORD }),
        ['body', 'email'],
      )
    })
  }

  test('password length: 7 rejected, 8 and 256 accepted, 257 rejected', async ({
    request,
  }) => {
    await expect422(
      await register(request, {
        email: uniqueEmail(),
        password: 'x'.repeat(7),
      }),
      ['body', 'password'],
    )
    expect(
      (
        await register(request, {
          email: uniqueEmail(),
          password: 'x'.repeat(8),
        })
      ).status(),
    ).toBe(201)
    const email256 = uniqueEmail()
    expect(
      (
        await register(request, { email: email256, password: 'p'.repeat(256) })
      ).status(),
    ).toBe(201)
    // The 256-char password really works for login.
    expect((await login(request, email256, 'p'.repeat(256))).status()).toBe(200)
    await expect422(
      await register(request, {
        email: uniqueEmail(),
        password: 'x'.repeat(257),
      }),
      ['body', 'password'],
    )
  })

  test('accepts a unicode password', async ({ request }) => {
    const email = uniqueEmail()
    const password = 'пароль-密码-🔑-ok'
    expect((await register(request, { email, password })).status()).toBe(201)
    expect((await login(request, email, password)).status()).toBe(200)
  })

  test('displayName: null and omitted are stored as null', async ({
    request,
  }) => {
    for (const data of [
      { email: uniqueEmail(), password: PASSWORD, displayName: null },
      { email: uniqueEmail(), password: PASSWORD },
    ]) {
      const res = await register(request, data)
      expect(res.status()).toBe(201)
      const me = await request.get(url('/auth/me'), {
        headers: bearer((await res.json()).access_token),
      })
      expect((await me.json()).displayName).toBeNull()
    }
  })

  test('displayName: empty, long, and unicode values are stored as sent', async ({
    request,
  }) => {
    // No length limit or blank check on displayName today.
    for (const displayName of ['', 'd'.repeat(1000), 'Zoë 日本 🚀']) {
      const res = await register(request, {
        email: uniqueEmail(),
        password: PASSWORD,
        displayName,
      })
      expect(res.status()).toBe(201)
      const me = await request.get(url('/auth/me'), {
        headers: bearer((await res.json()).access_token),
      })
      expect((await me.json()).displayName).toBe(displayName)
    }
  })

  test('422 for missing body or missing fields', async ({ request }) => {
    expect((await request.post(url('/auth/register'))).status()).toBe(422)
    await expect422(await register(request, { password: PASSWORD }), [
      'body',
      'email',
    ])
    await expect422(await register(request, { email: uniqueEmail() }), [
      'body',
      'password',
    ])
  })

  test('422 for wrong field types', async ({ request }) => {
    await expect422(
      await register(request, { email: uniqueEmail(), password: 12345678 }),
      ['body', 'password'],
    )
    await expect422(
      await register(request, { email: ['a@example.com'], password: PASSWORD }),
      ['body', 'email'],
    )
  })
})

// --- POST /auth/login ------------------------------------------------------

test.describe('POST /auth/login', () => {
  test('returns a token that authenticates /auth/me', async ({ request }) => {
    const user = await registerViaApi(request)
    const res = await login(request, user.email, PASSWORD)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body).toEqual({
      access_token: expect.any(String),
      token_type: 'bearer',
    })
    const me = await request.get(url('/auth/me'), {
      headers: bearer(body.access_token),
    })
    expect((await me.json()).id).toBe(user.id)
  })

  test('401 with the same message for wrong password and unknown email', async ({
    request,
  }) => {
    // Identical responses so the endpoint can't be used to find
    // registered emails.
    const user = await registerViaApi(request)
    const wrongPassword = await login(request, user.email, 'not-the-password')
    const unknownEmail = await login(request, uniqueEmail(), PASSWORD)
    for (const res of [wrongPassword, unknownEmail]) {
      expect(res.status()).toBe(401)
      expect(await res.json()).toEqual({
        detail: 'Incorrect email or password',
      })
      expect(res.headers()['www-authenticate']).toBe('Bearer')
    }
  })

  test('password is case-sensitive', async ({ request }) => {
    const user = await registerViaApi(request)
    expect(
      (await login(request, user.email, PASSWORD.toUpperCase())).status(),
    ).toBe(401)
  })

  test('422 when sent as JSON instead of a form', async ({ request }) => {
    const user = await registerViaApi(request)
    const res = await request.post(url('/auth/login'), {
      data: { username: user.email, password: PASSWORD },
    })
    expect(res.status()).toBe(422)
  })

  test('422 when username or password is missing', async ({ request }) => {
    await expect422(
      await request.post(url('/auth/login'), { form: { password: PASSWORD } }),
      ['body', 'username'],
    )
    await expect422(
      await request.post(url('/auth/login'), {
        form: { username: uniqueEmail() },
      }),
      ['body', 'password'],
    )
  })
})

// --- GET /auth/me and token handling ---------------------------------------

test.describe('GET /auth/me', () => {
  test('returns the current user with the expected schema', async ({
    request,
  }) => {
    const user = await registerViaApi(request, 'Me Myself')
    const res = await request.get(url('/auth/me'), {
      headers: bearer(user.token),
    })
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(Object.keys(body).sort()).toEqual(
      ['createdAt', 'displayName', 'email', 'id', 'updatedAt'].sort(),
    )
    expect(body).toMatchObject({
      id: user.id,
      email: user.email,
      displayName: 'Me Myself',
    })
    expect(body.createdAt).toMatch(ISO_DATETIME)
    // Never leaks the password hash.
    expect(JSON.stringify(body)).not.toMatch(/password|hash|argon/i)
  })

  test('401 "Not authenticated" without a bearer token', async ({
    request,
  }) => {
    for (const headers of [
      {} as Record<string, string>,
      { Authorization: 'Basic abc' },
      { Authorization: 'Token abc' },
    ]) {
      const res = await request.get(url('/auth/me'), { headers })
      expect(res.status()).toBe(401)
      expect(await res.json()).toEqual({ detail: 'Not authenticated' })
      expect(res.headers()['www-authenticate']).toBe('Bearer')
    }
  })

  test('401 for malformed tokens', async ({ request }) => {
    // Header values must be ASCII, so no unicode garbage here.
    for (const token of ['abc', 'abc.def', 'a.b.c', 'Bearer x', '%%%']) {
      const res = await request.get(url('/auth/me'), { headers: bearer(token) })
      expect(res.status()).toBe(401)
    }
  })

  test('401 for a tampered token signature', async ({ request }) => {
    const user = await registerViaApi(request)
    const [h, p, s] = user.token.split('.')
    const flipped = s[0] === 'A' ? `B${s.slice(1)}` : `A${s.slice(1)}`
    const res = await request.get(url('/auth/me'), {
      headers: bearer(`${h}.${p}.${flipped}`),
    })
    expect(res.status()).toBe(401)
    expect(await res.json()).toEqual({
      detail: 'Could not validate credentials',
    })
  })

  test('401 for a token signed with a different secret', async ({
    request,
  }) => {
    const user = await registerViaApi(request)
    const token = forgeToken(
      { sub: user.id, exp: Math.floor(Date.now() / 1000) + 300 },
      'some-other-secret',
    )
    expect(
      (await request.get(url('/auth/me'), { headers: bearer(token) })).status(),
    ).toBe(401)
  })

  test('401 for an alg=none token', async ({ request }) => {
    const user = await registerViaApi(request)
    const enc = (o: object) =>
      Buffer.from(JSON.stringify(o)).toString('base64url')
    const token = `${enc({ alg: 'none', typ: 'JWT' })}.${enc({
      sub: user.id,
      exp: Math.floor(Date.now() / 1000) + 300,
    })}.`
    expect(
      (await request.get(url('/auth/me'), { headers: bearer(token) })).status(),
    ).toBe(401)
  })

  test.describe('forged tokens (needs the server’s signing secret)', () => {
    let user: TestUser

    test.beforeEach(async ({ request }) => {
      user = await registerViaApi(request)
      test.skip(
        !(await canForgeTokens(request, user)),
        'Server is not using the dev JWT secret; set E2E_JWT_SECRET to match.',
      )
    })

    test('401 for an expired token', async ({ request }) => {
      const token = forgeToken({
        sub: user.id,
        exp: Math.floor(Date.now() / 1000) - 60,
      })
      const res = await request.get(url('/auth/me'), { headers: bearer(token) })
      expect(res.status()).toBe(401)
      expect(await res.json()).toEqual({
        detail: 'Could not validate credentials',
      })
    })

    test('401 for a valid token whose user does not exist', async ({
      request,
    }) => {
      const token = forgeToken({
        sub: crypto.randomUUID(),
        exp: Math.floor(Date.now() / 1000) + 300,
      })
      expect(
        (
          await request.get(url('/auth/me'), { headers: bearer(token) })
        ).status(),
      ).toBe(401)
    })

    test('401 for a token without a string sub', async ({ request }) => {
      const exp = Math.floor(Date.now() / 1000) + 300
      for (const payload of [{ exp }, { sub: 123, exp }]) {
        const res = await request.get(url('/auth/me'), {
          headers: bearer(forgeToken(payload)),
        })
        expect(res.status()).toBe(401)
      }
    })
  })
})

// --- logout ----------------------------------------------------------------

test.describe('logout', () => {
  test('there is no server-side logout endpoint', async ({ request }) => {
    // Logout is client-side only: the frontend drops the token from
    // localStorage (services/api/auth.ts). Tokens are stateless JWTs and
    // stay valid until they expire (ACCESS_TOKEN_EXPIRE_MINUTES).
    const user = await registerViaApi(request)
    const res = await request.post(url('/auth/logout'), {
      headers: bearer(user.token),
    })
    expect(res.status()).toBe(404)
    expect(
      (
        await request.get(url('/auth/me'), { headers: bearer(user.token) })
      ).status(),
    ).toBe(200)
  })
})

// --- authentication required -----------------------------------------------

test.describe('authenticated endpoints require a token', () => {
  const someId = '00000000-0000-0000-0000-000000000000'
  const endpoints: [string, string][] = [
    ['GET', '/auth/me'],
    ['GET', '/projects'],
    ['POST', '/projects'],
    ['GET', `/projects/${someId}`],
    ['PATCH', `/projects/${someId}`],
    ['DELETE', `/projects/${someId}`],
    ['GET', `/projects/${someId}/notes`],
    ['POST', `/projects/${someId}/notes`],
    ['DELETE', `/notes/${someId}`],
  ]
  for (const [method, path] of endpoints) {
    test(`${method} ${path.replace(someId, ':id')} → 401 without a token`, async ({
      request,
    }) => {
      const res = await request.fetch(url(path), { method, data: {} })
      expect(res.status()).toBe(401)
    })
  }
})

// --- projects --------------------------------------------------------------

test.describe('projects', () => {
  let user: TestUser

  test.beforeEach(async ({ request }) => {
    user = await registerViaApi(request)
  })

  const post = (request: APIRequestContext, data: unknown) =>
    request.post(url('/projects'), { headers: bearer(user.token), data })
  const patch = (request: APIRequestContext, id: string, data: unknown) =>
    request.patch(url(`/projects/${id}`), { headers: bearer(user.token), data })

  test.describe('POST /projects', () => {
    test('creates with defaults when only a name is given', async ({
      request,
    }) => {
      const res = await post(request, { name: 'Just a name' })
      expect(res.status()).toBe(201)
      const p = (await res.json()) as ApiProject
      expect(p).toEqual({
        id: expect.any(String),
        name: 'Just a name',
        pitch: '',
        description: '',
        status: 'Inbox',
        tags: [],
        excitement: 3,
        effort: 3,
        potential: 3,
        nextAction: '',
        targetDate: null,
        links: [],
        createdAt: expect.stringMatching(ISO_DATETIME),
        updatedAt: expect.stringMatching(ISO_DATETIME),
      })
    })

    test('stores every field', async ({ request }) => {
      const data = {
        name: `Full ${uid()}`,
        pitch: 'Pitch',
        description: 'Desc',
        status: 'Exploring',
        tags: ['a', 'b'],
        excitement: 5,
        effort: 1,
        potential: 4,
        nextAction: 'Do it',
        targetDate: '2030-06-15',
        links: [
          { label: 'Docs', url: 'https://example.com/docs' },
          { url: 'http://x.test' },
        ],
      }
      const p = (await (await post(request, data)).json()) as ApiProject
      expect(p).toMatchObject({
        ...data,
        links: [
          { label: 'Docs', url: 'https://example.com/docs' },
          { label: null, url: 'http://x.test' },
        ],
      })
      // Round-trips through GET.
      expect(
        await (await getProjectViaApi(request, user, p.id)).json(),
      ).toEqual(p)
    })

    test('accepts every status value', async ({ request }) => {
      for (const status of [
        'Inbox',
        'Exploring',
        'Active',
        'Parked',
        'Graduated',
        'Killed',
      ]) {
        const res = await post(request, { name: status, status })
        expect((await res.json()).status).toBe(status)
      }
    })

    test('422 for unknown or wrongly-cased status', async ({ request }) => {
      for (const status of ['Done', 'active', '', null]) {
        await expect422(await post(request, { name: 'x', status }), [
          'body',
          'status',
        ])
      }
    })

    test('422 when name is missing or not a string', async ({ request }) => {
      await expect422(await post(request, {}), ['body', 'name'])
      await expect422(await post(request, { name: null }), ['body', 'name'])
      await expect422(await post(request, { name: 42 }), ['body', 'name'])
    })

    test('empty and whitespace names are accepted (only the UI requires one)', async ({
      request,
    }) => {
      // Current behavior: the API has no min length on name; the quick
      // capture form is what enforces "name required" (docs/specs.md).
      for (const name of ['', '   ']) {
        const res = await post(request, { name })
        expect(res.status()).toBe(201)
        expect((await res.json()).name).toBe(name)
      }
    })

    test('long and unicode names are stored exactly', async ({ request }) => {
      for (const name of [
        'n'.repeat(10_000),
        '日本語 🚀 émoji Ünïcödé',
        'RTL ‮txet‬ and zero​width',
        '<script>alert(1)</script>',
        "Robert'); DROP TABLE projects;--",
      ]) {
        const res = await post(request, { name })
        expect(res.status()).toBe(201)
        expect((await res.json()).name).toBe(name)
      }
    })

    test('scores: 1 and 5 accepted; 0, 6, -1 rejected', async ({ request }) => {
      for (const field of ['excitement', 'effort', 'potential']) {
        for (const ok of [1, 5]) {
          expect(
            (await post(request, { name: 's', [field]: ok })).status(),
          ).toBe(201)
        }
        for (const bad of [0, 6, -1]) {
          await expect422(await post(request, { name: 's', [field]: bad }), [
            'body',
            field,
          ])
        }
      }
    })

    test('scores: null and fractional values rejected; integral floats coerced', async ({
      request,
    }) => {
      await expect422(await post(request, { name: 's', excitement: null }), [
        'body',
        'excitement',
      ])
      await expect422(await post(request, { name: 's', excitement: 2.5 }), [
        'body',
        'excitement',
      ])
      await expect422(await post(request, { name: 's', excitement: 'high' }), [
        'body',
        'excitement',
      ])
      // Pydantic's lax mode turns 3.0 and "3" into 3.
      expect(
        (await (await post(request, { name: 's', excitement: 3.0 })).json())
          .excitement,
      ).toBe(3)
      expect(
        (await (await post(request, { name: 's', excitement: '4' })).json())
          .excitement,
      ).toBe(4)
    })

    test('target dates: past, future and null accepted', async ({
      request,
    }) => {
      for (const targetDate of [
        '2000-01-01',
        isoDateFromToday(0),
        '2999-12-31',
        null,
      ]) {
        const res = await post(request, { name: 'd', targetDate })
        expect(res.status()).toBe(201)
        expect((await res.json()).targetDate).toBe(targetDate)
      }
    })

    test('target dates: impossible or malformed rejected', async ({
      request,
    }) => {
      for (const targetDate of [
        '2024-02-30',
        '2023-13-01',
        'not-a-date',
        '2024-1-5',
        '15/06/2030',
      ]) {
        await expect422(await post(request, { name: 'd', targetDate }), [
          'body',
          'targetDate',
        ])
      }
    })

    test('target date accepts a leap day', async ({ request }) => {
      expect(
        (
          await (
            await post(request, { name: 'd', targetDate: '2028-02-29' })
          ).json()
        ).targetDate,
      ).toBe('2028-02-29')
    })

    test('tags are stored as sent: no dedupe, case kept, long values allowed', async ({
      request,
    }) => {
      // The API does not normalize tags; the UI lowercases (and on the
      // detail page, dedupes) before sending.
      const tags = ['a', 'a', 'A', 't'.repeat(1000), 'émoji-🚀']
      const res = await post(request, { name: 't', tags })
      expect(res.status()).toBe(201)
      expect((await res.json()).tags).toEqual(tags)
    })

    test('422 for tags that are not a list of strings', async ({ request }) => {
      await expect422(await post(request, { name: 't', tags: 'a,b' }), [
        'body',
        'tags',
      ])
      await expect422(await post(request, { name: 't', tags: [1] }), [
        'body',
        'tags',
        0,
      ])
    })

    test('links must be http(s); javascript: and other schemes rejected', async ({
      request,
    }) => {
      for (const bad of [
        'javascript:alert(1)',
        'ftp://x.test',
        'example.com',
        'data:text/html,hi',
      ]) {
        await expect422(
          await post(request, { name: 'l', links: [{ url: bad }] }),
          ['body', 'links', 0, 'url'],
        )
      }
      expect(
        (
          await post(request, {
            name: 'l',
            links: [{ url: 'HTTPS://EXAMPLE.COM' }],
          })
        ).status(),
      ).toBe(201)
    })

    test('unknown fields are ignored, and server-owned fields cannot be set', async ({
      request,
    }) => {
      const res = await post(request, {
        name: 'x',
        bogus: 1,
        id: 'chosen-id',
        createdAt: '2000-01-01T00:00:00Z',
        ownerId: 'someone-else',
      })
      expect(res.status()).toBe(201)
      const p = await res.json()
      expect(p.id).not.toBe('chosen-id')
      expect(p.createdAt).not.toContain('2000-01-01')
      expect(p).not.toHaveProperty('bogus')
      expect(p).not.toHaveProperty('ownerId')
    })

    test('422 for a non-JSON body', async ({ request }) => {
      const res = await request.post(url('/projects'), {
        headers: { ...bearer(user.token), 'Content-Type': 'application/json' },
        data: 'not json',
      })
      expect(res.status()).toBe(422)
    })
  })

  test.describe('GET /projects', () => {
    test('empty list for a new user', async ({ request }) => {
      const res = await request.get(url('/projects'), {
        headers: bearer(user.token),
      })
      expect(res.status()).toBe(200)
      expect(await res.json()).toEqual([])
    })

    test('lists exactly the user’s projects', async ({ request }) => {
      const a = await createProjectViaApi(request, user, { name: 'A' })
      const b = await createProjectViaApi(request, user, { name: 'B' })
      const res = await request.get(url('/projects'), {
        headers: bearer(user.token),
      })
      const ids = ((await res.json()) as ApiProject[]).map((p) => p.id)
      expect(ids.sort()).toEqual([a.id, b.id].sort())
    })
  })

  test.describe('GET /projects/:id', () => {
    test('returns the project', async ({ request }) => {
      const p = await createProjectViaApi(request, user, { name: 'One' })
      const res = await getProjectViaApi(request, user, p.id)
      expect(res.status()).toBe(200)
      expect(await res.json()).toEqual(p)
    })

    test('404 for a nonexistent or malformed id', async ({ request }) => {
      for (const id of [crypto.randomUUID(), 'nope', '1']) {
        const res = await getProjectViaApi(request, user, id)
        expect(res.status()).toBe(404)
        expect(await res.json()).toEqual({ detail: 'Project not found' })
      }
    })
  })

  test.describe('PATCH /projects/:id', () => {
    let project: ApiProject

    test.beforeEach(async ({ request }) => {
      project = await createProjectViaApi(request, user, {
        name: 'Original',
        pitch: 'Original pitch',
        tags: ['keep'],
        excitement: 2,
        targetDate: '2030-01-01',
      })
    })

    test('updates only the fields sent', async ({ request }) => {
      const res = await patch(request, project.id, { pitch: 'New pitch' })
      expect(res.status()).toBe(200)
      const updated = (await res.json()) as ApiProject
      expect(updated).toEqual({
        ...project,
        pitch: 'New pitch',
        updatedAt: expect.any(String),
      })
      expect(updated.createdAt).toBe(project.createdAt)
      expect(Date.parse(updated.updatedAt)).toBeGreaterThanOrEqual(
        Date.parse(project.updatedAt),
      )
    })

    test('updates every editable field at once', async ({ request }) => {
      const changes = {
        name: 'Changed',
        pitch: 'p',
        description: 'd',
        status: 'Graduated',
        tags: ['x', 'y'],
        excitement: 5,
        effort: 5,
        potential: 1,
        nextAction: 'n',
        targetDate: '2031-12-31',
        links: [{ label: 'L', url: 'https://l.test' }],
      }
      const updated = await (await patch(request, project.id, changes)).json()
      expect(updated).toMatchObject(changes)
      expect(
        await (await getProjectViaApi(request, user, project.id)).json(),
      ).toMatchObject(changes)
    })

    test('empty body is a no-op 200', async ({ request }) => {
      const res = await patch(request, project.id, {})
      expect(res.status()).toBe(200)
      expect(await res.json()).toMatchObject({
        name: 'Original',
        tags: ['keep'],
      })
    })

    test('targetDate: null clears the date', async ({ request }) => {
      const res = await patch(request, project.id, { targetDate: null })
      expect(res.status()).toBe(200)
      expect((await res.json()).targetDate).toBeNull()
    })

    test('validation matches create: scores, status, dates, links', async ({
      request,
    }) => {
      await expect422(await patch(request, project.id, { excitement: 6 }), [
        'body',
        'excitement',
      ])
      await expect422(await patch(request, project.id, { effort: 0 }), [
        'body',
        'effort',
      ])
      await expect422(await patch(request, project.id, { status: 'Done' }), [
        'body',
        'status',
      ])
      await expect422(
        await patch(request, project.id, { targetDate: '2024-02-30' }),
        ['body', 'targetDate'],
      )
      await expect422(
        await patch(request, project.id, { links: [{ url: 'javascript:x' }] }),
        ['body', 'links', 0, 'url'],
      )
      // Nothing was changed by the rejected requests.
      expect(
        await (await getProjectViaApi(request, user, project.id)).json(),
      ).toMatchObject({
        excitement: 2,
        status: 'Inbox',
        targetDate: '2030-01-01',
      })
    })

    test('404 for a nonexistent project', async ({ request }) => {
      const res = await patch(request, crypto.randomUUID(), { name: 'x' })
      expect(res.status()).toBe(404)
    })

    test('PUT is not allowed', async ({ request }) => {
      const res = await request.put(url(`/projects/${project.id}`), {
        headers: bearer(user.token),
        data: { name: 'x' },
      })
      expect(res.status()).toBe(405)
    })

    // Only targetDate may be null. Before this was validated, a null for
    // any other field was a 500, and for tags/links it was saved and broke
    // every later read of the project, including GET /projects for the
    // whole account.
    for (const field of [
      'name',
      'pitch',
      'description',
      'status',
      'nextAction',
      'excitement',
      'effort',
      'potential',
      'tags',
      'links',
    ]) {
      test(`explicit null for ${field} is rejected and leaves the project intact`, async ({
        request,
      }) => {
        const res = await patch(request, project.id, { [field]: null })
        await expect422(res, ['body', field])
        expect(
          (await getProjectViaApi(request, user, project.id)).status(),
        ).toBe(200)
        const list = await request.get(url('/projects'), {
          headers: bearer(user.token),
        })
        expect(list.status()).toBe(200)
      })
    }
  })

  test.describe('DELETE /projects/:id', () => {
    test('deletes, then 404s on every route', async ({ request }) => {
      const p = await createProjectViaApi(request, user, { name: 'Gone' })
      const res = await request.delete(url(`/projects/${p.id}`), {
        headers: bearer(user.token),
      })
      expect(res.status()).toBe(204)
      expect(await res.text()).toBe('')

      expect((await getProjectViaApi(request, user, p.id)).status()).toBe(404)
      expect((await patch(request, p.id, { name: 'x' })).status()).toBe(404)
      expect(
        (
          await request.delete(url(`/projects/${p.id}`), {
            headers: bearer(user.token),
          })
        ).status(),
      ).toBe(404)
      const list = await request.get(url('/projects'), {
        headers: bearer(user.token),
      })
      expect(await list.json()).toEqual([])
    })

    test('cascades to the project’s notes', async ({ request }) => {
      const p = await createProjectViaApi(request, user, { name: 'With notes' })
      const n1 = await addNoteViaApi(request, user, p.id, 'one')
      const n2 = await addNoteViaApi(request, user, p.id, 'two')
      await request.delete(url(`/projects/${p.id}`), {
        headers: bearer(user.token),
      })

      expect(
        (
          await request.get(url(`/projects/${p.id}/notes`), {
            headers: bearer(user.token),
          })
        ).status(),
      ).toBe(404)
      for (const n of [n1, n2]) {
        const res = await request.delete(url(`/notes/${n.id}`), {
          headers: bearer(user.token),
        })
        expect(res.status()).toBe(404)
      }
    })

    test('leaves the user’s other projects alone', async ({ request }) => {
      const keep = await createProjectViaApi(request, user, { name: 'Keep' })
      await addNoteViaApi(request, user, keep.id, 'still here')
      const drop = await createProjectViaApi(request, user, { name: 'Drop' })
      await request.delete(url(`/projects/${drop.id}`), {
        headers: bearer(user.token),
      })
      expect((await getProjectViaApi(request, user, keep.id)).status()).toBe(
        200,
      )
      expect(await listNotesViaApi(request, user, keep.id)).toHaveLength(1)
    })
  })
})

// --- notes -----------------------------------------------------------------

test.describe('notes', () => {
  let user: TestUser
  let project: ApiProject

  test.beforeEach(async ({ request }) => {
    user = await registerViaApi(request)
    project = await createProjectViaApi(request, user, {
      name: `Noted ${uid()}`,
    })
  })

  const addNote = (
    request: APIRequestContext,
    projectId: string,
    data: unknown,
  ) =>
    request.post(url(`/projects/${projectId}/notes`), {
      headers: bearer(user.token),
      data,
    })

  test.describe('POST /projects/:id/notes', () => {
    test('creates a note and returns it with the touched project', async ({
      request,
    }) => {
      const res = await addNote(request, project.id, { body: 'First note' })
      expect(res.status()).toBe(201)
      const body = (await res.json()) as { note: ApiNote; project: ApiProject }
      expect(body.note).toEqual({
        id: expect.any(String),
        projectId: project.id,
        body: 'First note',
        createdAt: expect.stringMatching(ISO_DATETIME),
      })
      expect(body.project.id).toBe(project.id)
      // Adding a note bumps the project's updatedAt.
      expect(Date.parse(body.project.updatedAt)).toBeGreaterThanOrEqual(
        Date.parse(project.updatedAt),
      )
    })

    test('long, multi-line and unicode bodies are stored exactly', async ({
      request,
    }) => {
      for (const text of [
        'z'.repeat(100_000),
        'line 1\nline 2\n\n  indented',
        '日本 🚀 <b>x</b>',
      ]) {
        const res = await addNote(request, project.id, { body: text })
        expect(res.status()).toBe(201)
        expect((await res.json()).note.body).toBe(text)
      }
    })

    test('empty and whitespace bodies are accepted (only the UI blocks them)', async ({
      request,
    }) => {
      for (const text of ['', '   ']) {
        const res = await addNote(request, project.id, { body: text })
        expect(res.status()).toBe(201)
        expect((await res.json()).note.body).toBe(text)
      }
    })

    test('422 for null, missing, or non-string body', async ({ request }) => {
      await expect422(await addNote(request, project.id, { body: null }), [
        'body',
        'body',
      ])
      await expect422(await addNote(request, project.id, {}), ['body', 'body'])
      await expect422(await addNote(request, project.id, { body: 42 }), [
        'body',
        'body',
      ])
    })

    test('404 for a nonexistent or deleted project', async ({ request }) => {
      expect(
        (await addNote(request, crypto.randomUUID(), { body: 'x' })).status(),
      ).toBe(404)
      await request.delete(url(`/projects/${project.id}`), {
        headers: bearer(user.token),
      })
      const res = await addNote(request, project.id, { body: 'x' })
      expect(res.status()).toBe(404)
      expect(await res.json()).toEqual({ detail: 'Project not found' })
    })
  })

  test.describe('GET /projects/:id/notes', () => {
    test('empty for a new project', async ({ request }) => {
      expect(await listNotesViaApi(request, user, project.id)).toEqual([])
    })

    test('lists only this project’s notes, newest first', async ({
      request,
    }) => {
      const other = await createProjectViaApi(request, user, { name: 'Other' })
      await addNoteViaApi(request, user, other.id, 'elsewhere')
      const first = await addNoteViaApi(request, user, project.id, 'first')
      const second = await addNoteViaApi(request, user, project.id, 'second')
      const notes = await listNotesViaApi(request, user, project.id)
      expect(notes.map((n) => n.id)).toEqual([second.id, first.id])
    })

    test('404 for a nonexistent project', async ({ request }) => {
      const res = await request.get(
        url(`/projects/${crypto.randomUUID()}/notes`),
        {
          headers: bearer(user.token),
        },
      )
      expect(res.status()).toBe(404)
    })
  })

  test.describe('DELETE /notes/:id', () => {
    test('deletes the note and returns the touched project', async ({
      request,
    }) => {
      const keep = await addNoteViaApi(request, user, project.id, 'keep')
      const drop = await addNoteViaApi(request, user, project.id, 'drop')
      const res = await request.delete(url(`/notes/${drop.id}`), {
        headers: bearer(user.token),
      })
      expect(res.status()).toBe(200)
      expect((await res.json()).id).toBe(project.id)
      expect(
        (await listNotesViaApi(request, user, project.id)).map((n) => n.id),
      ).toEqual([keep.id])
    })

    test('404 for a nonexistent or already-deleted note', async ({
      request,
    }) => {
      const n = await addNoteViaApi(request, user, project.id, 'once')
      const del = () =>
        request.delete(url(`/notes/${n.id}`), { headers: bearer(user.token) })
      expect((await del()).status()).toBe(200)
      const again = await del()
      expect(again.status()).toBe(404)
      expect(await again.json()).toEqual({ detail: 'Note not found' })
      expect(
        (
          await request.delete(url(`/notes/${crypto.randomUUID()}`), {
            headers: bearer(user.token),
          })
        ).status(),
      ).toBe(404)
    })
  })

  test('notes cannot be edited, and have no project-nested routes', async ({
    request,
  }) => {
    // docs/specs.md: "a notes log with add and delete". No edit endpoint.
    const n = await addNoteViaApi(request, user, project.id, 'fixed')
    const h = { headers: bearer(user.token), data: { body: 'changed' } }
    expect((await request.patch(url(`/notes/${n.id}`), h)).status()).toBe(405)
    expect(
      (
        await request.patch(url(`/projects/${project.id}/notes/${n.id}`), h)
      ).status(),
    ).toBe(404)
    expect(
      (
        await request.delete(url(`/projects/${project.id}/notes/${n.id}`), {
          headers: bearer(user.token),
        })
      ).status(),
    ).toBe(404)
    expect((await listNotesViaApi(request, user, project.id))[0].body).toBe(
      'fixed',
    )
  })
})

// --- isolation -------------------------------------------------------------

test.describe('user isolation', () => {
  // Another user's records answer 404, not 403, with the same message as
  // a truly missing record, so ids can't be probed for existence.
  let alice: TestUser
  let bob: TestUser
  let project: ApiProject
  let note: ApiNote

  test.beforeEach(async ({ request }) => {
    alice = await registerViaApi(request)
    bob = await registerViaApi(request)
    project = await createProjectViaApi(request, alice, {
      name: `Alice only ${uid()}`,
      tags: ['secret'],
    })
    note = await addNoteViaApi(request, alice, project.id, 'private note')
  })

  test('B does not see A’s projects in the list', async ({ request }) => {
    await createProjectViaApi(request, bob, { name: 'Bob’s' })
    const res = await request.get(url('/projects'), {
      headers: bearer(bob.token),
    })
    const names = ((await res.json()) as ApiProject[]).map((p) => p.name)
    expect(names).toEqual(['Bob’s'])
  })

  test('B cannot read, edit, or delete A’s project', async ({ request }) => {
    const h = bearer(bob.token)
    for (const res of [
      await request.get(url(`/projects/${project.id}`), { headers: h }),
      await request.patch(url(`/projects/${project.id}`), {
        headers: h,
        data: { name: 'pwned' },
      }),
      await request.delete(url(`/projects/${project.id}`), { headers: h }),
    ]) {
      expect(res.status()).toBe(404)
      expect(await res.json()).toEqual({ detail: 'Project not found' })
    }
    // A's project is untouched.
    const mine = await getProjectViaApi(request, alice, project.id)
    expect((await mine.json()).name).toBe(project.name)
  })

  test('B cannot list, add, or delete A’s notes', async ({ request }) => {
    const h = bearer(bob.token)
    expect(
      (
        await request.get(url(`/projects/${project.id}/notes`), { headers: h })
      ).status(),
    ).toBe(404)
    expect(
      (
        await request.post(url(`/projects/${project.id}/notes`), {
          headers: h,
          data: { body: 'x' },
        })
      ).status(),
    ).toBe(404)
    const del = await request.delete(url(`/notes/${note.id}`), { headers: h })
    expect(del.status()).toBe(404)
    // Same body as a note that doesn't exist at all.
    expect(await del.json()).toEqual({ detail: 'Note not found' })
    expect(
      (await listNotesViaApi(request, alice, project.id)).map((n) => n.body),
    ).toEqual(['private note'])
  })

  test('B’s token for /auth/me returns B, never A', async ({ request }) => {
    const me = await request.get(url('/auth/me'), {
      headers: bearer(bob.token),
    })
    expect((await me.json()).id).toBe(bob.id)
  })
})

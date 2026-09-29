import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mockToken = vi.hoisted(() => ({ getToken: vi.fn() }))
vi.mock('./token', () => mockToken)

const { HttpError, httpRequest, setUnauthorizedHandler } =
  await import('./http')

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

beforeEach(() => {
  vi.restoreAllMocks()
  mockToken.getToken.mockReturnValue(null)
  setUnauthorizedHandler(null)
})

describe('bearer token', () => {
  it('attaches the token when present', async () => {
    mockToken.getToken.mockReturnValue('secret-token')
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }))

    await httpRequest('/projects')

    const [, init] = fetchSpy.mock.calls[0]
    expect((init?.headers as Record<string, string>)['Authorization']).toBe(
      'Bearer secret-token',
    )
  })

  it('omits the header when there is no token', async () => {
    mockToken.getToken.mockReturnValue(null)
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }))

    await httpRequest('/projects')

    const [, init] = fetchSpy.mock.calls[0]
    expect(init?.headers as Record<string, string>).not.toHaveProperty(
      'Authorization',
    )
  })

  it('omits the header when skipAuth is set, even with a stored token', async () => {
    mockToken.getToken.mockReturnValue('secret-token')
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }))

    await httpRequest('/auth/login', { skipAuth: true })

    const [, init] = fetchSpy.mock.calls[0]
    expect(init?.headers as Record<string, string>).not.toHaveProperty(
      'Authorization',
    )
  })
})

describe('error parsing', () => {
  it('parses a string detail into an HttpError', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      jsonResponse(404, { detail: 'Project not found' }),
    )

    const rejection = httpRequest('/projects/x')
    await expect(rejection).rejects.toBeInstanceOf(HttpError)
    await expect(rejection).rejects.toMatchObject({
      status: 404,
      message: 'Project not found',
    })
  })

  it('parses a FastAPI validation-error array detail into an HttpError', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      jsonResponse(422, {
        detail: [{ loc: ['body', 'email'], msg: 'field required' }],
      }),
    )

    await expect(httpRequest('/auth/register')).rejects.toMatchObject({
      status: 422,
      message: 'field required',
    })
  })

  it('falls back to status text when the body is not JSON', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response('not json', { status: 500, statusText: 'Server Error' }),
    )

    await expect(httpRequest('/projects')).rejects.toMatchObject({
      status: 500,
      message: 'Server Error',
    })
  })
})

describe('unauthorized handler', () => {
  it('fires on a 401 when a token was attached', async () => {
    mockToken.getToken.mockReturnValue('expired-token')
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      jsonResponse(401, { detail: 'Not authenticated' }),
    )

    await expect(httpRequest('/projects')).rejects.toBeInstanceOf(HttpError)
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('does not fire on a 401 with no token attached (e.g. bad login)', async () => {
    mockToken.getToken.mockReturnValue(null)
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      jsonResponse(401, { detail: 'Incorrect email or password' }),
    )

    await expect(
      httpRequest('/auth/login', { skipAuth: true }),
    ).rejects.toBeInstanceOf(HttpError)
    expect(handler).not.toHaveBeenCalled()
  })

  it('does not fire on other failures', async () => {
    mockToken.getToken.mockReturnValue('secret-token')
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      jsonResponse(500, { detail: 'boom' }),
    )

    await expect(httpRequest('/projects')).rejects.toBeInstanceOf(HttpError)
    expect(handler).not.toHaveBeenCalled()
  })
})

describe('response handling', () => {
  it('returns undefined for a 204 No Content', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(null, { status: 204 }),
    )

    await expect(httpRequest('/projects/x')).resolves.toBeUndefined()
  })

  it('returns the parsed JSON body on success', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      jsonResponse(200, { id: 'p1' }),
    )

    await expect(httpRequest('/projects/p1')).resolves.toEqual({ id: 'p1' })
  })
})

describe('request URL', () => {
  async function requestedUrl(path: string): Promise<string> {
    vi.resetModules()
    const { httpRequest: freshHttpRequest } = await import('./http')
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }))

    await freshHttpRequest(path)

    return String(fetchSpy.mock.lastCall?.[0])
  }

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('prefixes paths with /api by default (same-origin behind CloudFront)', async () => {
    vi.stubEnv('VITE_API_BASE_URL', undefined)

    expect(await requestedUrl('/projects')).toBe('/api/projects')
    expect(await requestedUrl('/projects/abc/notes')).toBe(
      '/api/projects/abc/notes',
    )
  })

  it('prefixes paths with VITE_API_BASE_URL when set (local uvicorn)', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://localhost:8000')

    expect(await requestedUrl('/projects')).toBe(
      'http://localhost:8000/projects',
    )
    expect(await requestedUrl('/auth/login')).toBe(
      'http://localhost:8000/auth/login',
    )
  })
})

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

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
  setUnauthorizedHandler(null)
})

describe('session cookie', () => {
  it('sends credentials so the browser attaches the httpOnly cookie', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }))

    await httpRequest('/projects')

    const [, init] = fetchSpy.mock.calls[0]
    expect(init?.credentials).toBe('include')
  })

  it('never sets an Authorization header itself', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }))

    await httpRequest('/projects')

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
  it('fires on a 401 (expired or invalid session)', async () => {
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      jsonResponse(401, { detail: 'Not authenticated' }),
    )

    await expect(httpRequest('/projects')).rejects.toBeInstanceOf(HttpError)
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('does not fire on a 401 with ignoreUnauthorized set (e.g. bad login)', async () => {
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      jsonResponse(401, { detail: 'Incorrect email or password' }),
    )

    await expect(
      httpRequest('/auth/login', { ignoreUnauthorized: true }),
    ).rejects.toBeInstanceOf(HttpError)
    expect(handler).not.toHaveBeenCalled()
  })

  it('does not fire on other failures', async () => {
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

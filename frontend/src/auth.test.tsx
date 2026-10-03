import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { HttpError, type User } from '@/services/api'
import { AuthProvider, SESSION_RETRY_DELAY_MS } from '@/auth.tsx'
import { useAuth } from '@/use-auth'
import { act, flush, renderHook } from '@/lib/render-hook'

const mockAuthApi = vi.hoisted(() => ({
  register: vi.fn(),
  login: vi.fn(),
  // No session (a 401) unless a test says otherwise; set in beforeEach,
  // since HttpError can't be imported into this hoisted block.
  getCurrentUser: vi.fn(),
  logout: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/api')>()
  return { ...actual, authApi: mockAuthApi }
})

function user(overrides: Partial<User> = {}): User {
  return {
    id: 'u1',
    email: 'rob@example.com',
    displayName: null,
    createdAt: '2026-09-01T00:00:00Z',
    updatedAt: '2026-09-01T00:00:00Z',
    ...overrides,
  }
}

function setup() {
  return renderHook(() => useAuth(), { wrapper: AuthProvider })
}

beforeEach(() => {
  vi.clearAllMocks()
  mockAuthApi.getCurrentUser.mockRejectedValue(
    new HttpError(401, 'Not authenticated'),
  )
})

describe('on-mount session check', () => {
  it('starts loading and asks the server, since the cookie is unreadable', async () => {
    const hook = setup()
    expect(hook.result.status).toBe('loading')

    await flush()
    expect(mockAuthApi.getCurrentUser).toHaveBeenCalledTimes(1)
  })

  it('ends authenticated when the session cookie validates', async () => {
    const current = user()
    mockAuthApi.getCurrentUser.mockResolvedValueOnce(current)

    const hook = setup()
    await flush()

    expect(hook.result.status).toBe('authenticated')
    expect(hook.result.user).toEqual(current)
  })

  it('ends unauthenticated when there is no valid session', async () => {
    const hook = setup()
    await flush()

    expect(hook.result.status).toBe('unauthenticated')
    expect(hook.result.user).toBeNull()
    // The 401 isn't a mid-session expiry, so no logout request either.
    expect(mockAuthApi.logout).not.toHaveBeenCalled()
  })
})

describe('session check when the backend is unavailable', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout'] })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // flush() waits on a real setTimeout, which is faked here: advance the
  // fake clock instead (which also drains pending promises).
  async function tick(ms = 0) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ms)
    })
  }

  const waitOutRetryDelay = () => tick(SESSION_RETRY_DELAY_MS)

  it('retries once after a network error and signs in if that works', async () => {
    const current = user()
    mockAuthApi.getCurrentUser
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(current)

    const hook = setup()
    await tick()
    // Still loading during the retry delay: never bounced to login.
    expect(hook.result.status).toBe('loading')

    await waitOutRetryDelay()

    expect(mockAuthApi.getCurrentUser).toHaveBeenCalledTimes(2)
    expect(hook.result.status).toBe('authenticated')
    expect(hook.result.user).toEqual(current)
  })

  it('retries once after a 5xx, and a 401 on the retry means signed out', async () => {
    mockAuthApi.getCurrentUser.mockRejectedValueOnce(
      new HttpError(503, 'Service Unavailable'),
    )

    const hook = setup()
    await tick()
    await waitOutRetryDelay()

    expect(mockAuthApi.getCurrentUser).toHaveBeenCalledTimes(2)
    expect(hook.result.status).toBe('unauthenticated')
  })

  it('ends unreachable, not unauthenticated, when both attempts fail', async () => {
    mockAuthApi.getCurrentUser.mockRejectedValue(
      new TypeError('Failed to fetch'),
    )

    const hook = setup()
    await tick()
    await waitOutRetryDelay()

    expect(mockAuthApi.getCurrentUser).toHaveBeenCalledTimes(2)
    expect(hook.result.status).toBe('unreachable')
    expect(hook.result.user).toBeNull()
    expect(mockAuthApi.logout).not.toHaveBeenCalled()
  })

  it('does not retry a 401', async () => {
    const hook = setup()
    await tick()
    await waitOutRetryDelay()

    expect(mockAuthApi.getCurrentUser).toHaveBeenCalledTimes(1)
    expect(hook.result.status).toBe('unauthenticated')
  })

  it('retry() checks again from the unreachable state', async () => {
    const current = user()
    mockAuthApi.getCurrentUser
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(current)

    const hook = setup()
    await tick()
    await waitOutRetryDelay()
    expect(hook.result.status).toBe('unreachable')

    act(() => hook.result.retry())
    expect(hook.result.status).toBe('loading')
    await tick()

    expect(mockAuthApi.getCurrentUser).toHaveBeenCalledTimes(3)
    expect(hook.result.status).toBe('authenticated')
  })
})

describe('login', () => {
  it('sets user/status to authenticated on success', async () => {
    const hook = setup()
    await flush()

    const current = user({ email: 'me@example.com' })
    mockAuthApi.login.mockResolvedValueOnce(current)

    await act(async () => {
      await hook.result.login('me@example.com', 'correct-password')
    })

    expect(hook.result.status).toBe('authenticated')
    expect(hook.result.user).toEqual(current)
  })

  it('surfaces an error and does not authenticate on failure', async () => {
    const hook = setup()
    await flush()

    mockAuthApi.login.mockRejectedValueOnce(
      new Error('Incorrect email or password'),
    )

    await expect(
      act(async () => {
        await hook.result.login('me@example.com', 'wrong-password')
      }),
    ).rejects.toThrow('Incorrect email or password')

    expect(hook.result.status).toBe('unauthenticated')
    expect(hook.result.user).toBeNull()
  })
})

describe('register', () => {
  it('sets user/status to authenticated on success', async () => {
    const hook = setup()
    await flush()

    const current = user({ email: 'new@example.com' })
    mockAuthApi.register.mockResolvedValueOnce(current)

    await act(async () => {
      await hook.result.register({
        email: 'new@example.com',
        password: 'password123',
      })
    })

    expect(hook.result.status).toBe('authenticated')
    expect(hook.result.user).toEqual(current)
  })

  it('surfaces an error and does not authenticate on failure', async () => {
    const hook = setup()
    await flush()

    mockAuthApi.register.mockRejectedValueOnce(
      new Error('Email already registered'),
    )

    await expect(
      act(async () => {
        await hook.result.register({
          email: 'dupe@example.com',
          password: 'password123',
        })
      }),
    ).rejects.toThrow('Email already registered')

    expect(hook.result.status).toBe('unauthenticated')
    expect(hook.result.user).toBeNull()
  })
})

describe('logout', () => {
  it('asks the server to clear the cookie and resets to unauthenticated', async () => {
    mockAuthApi.getCurrentUser.mockResolvedValueOnce(user())
    const hook = setup()
    await flush()
    expect(hook.result.status).toBe('authenticated')

    act(() => {
      hook.result.logout()
    })

    expect(mockAuthApi.logout).toHaveBeenCalledTimes(1)
    expect(hook.result.status).toBe('unauthenticated')
    expect(hook.result.user).toBeNull()
  })

  it('still signs out locally when the logout request fails', async () => {
    mockAuthApi.getCurrentUser.mockResolvedValueOnce(user())
    mockAuthApi.logout.mockRejectedValueOnce(new Error('offline'))
    const hook = setup()
    await flush()

    act(() => {
      hook.result.logout()
    })
    await flush()

    expect(hook.result.status).toBe('unauthenticated')
    expect(hook.result.user).toBeNull()
  })
})

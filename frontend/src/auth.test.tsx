// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { User } from '@/services/api'
import { AuthProvider } from '@/auth.tsx'
import { useAuth } from '@/use-auth'
import { act, flush, renderHook } from '@/lib/render-hook'

const mockAuthApi = vi.hoisted(() => ({
  register: vi.fn(),
  login: vi.fn(),
  getCurrentUser: vi.fn(),
  logout: vi.fn(),
}))

const mockToken = vi.hoisted(() => ({
  getToken: vi.fn(),
  setToken: vi.fn(),
  clearToken: vi.fn(),
}))

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/api')>()
  return { ...actual, authApi: mockAuthApi }
})

vi.mock('@/services/api/token', () => mockToken)

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
  mockToken.getToken.mockReturnValue(null)
})

describe('on-mount token check', () => {
  it('starts unauthenticated with no stored token, and does not call getCurrentUser', async () => {
    mockToken.getToken.mockReturnValue(null)

    const hook = setup()
    await flush()

    expect(hook.result.status).toBe('unauthenticated')
    expect(hook.result.user).toBeNull()
    expect(mockAuthApi.getCurrentUser).not.toHaveBeenCalled()
  })

  it('ends authenticated when the stored token validates', async () => {
    mockToken.getToken.mockReturnValue('valid-token')
    const current = user()
    mockAuthApi.getCurrentUser.mockResolvedValueOnce(current)

    const hook = setup()
    await flush()

    expect(hook.result.status).toBe('authenticated')
    expect(hook.result.user).toEqual(current)
    expect(mockToken.clearToken).not.toHaveBeenCalled()
  })

  it('ends unauthenticated and clears the token when it fails validation', async () => {
    mockToken.getToken.mockReturnValue('stale-token')
    mockAuthApi.getCurrentUser.mockRejectedValueOnce(new Error('401'))

    const hook = setup()
    await flush()

    expect(hook.result.status).toBe('unauthenticated')
    expect(hook.result.user).toBeNull()
    expect(mockToken.clearToken).toHaveBeenCalledTimes(1)
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
  it('clears the token and resets to unauthenticated', async () => {
    mockToken.getToken.mockReturnValue('valid-token')
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
})

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import {
  authApi,
  HttpError,
  type RegisterInput,
  type User,
} from '@/services/api'
import { setUnauthorizedHandler } from '@/services/api/http'
import { AuthContext, type AuthStatus, type AuthValue } from '@/auth-context'

/** Wait before the one retry of a failed session check. */
export const SESSION_RETRY_DELAY_MS = 500

/** Only a 401 means "no valid session". */
function isSignedOut(err: unknown): boolean {
  return err instanceof HttpError && err.status === 401
}

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

/**
 * Ask the server who's signed in. Resolves to the user, or null on a 401.
 * Anything else (no response, a 5xx: the backend or its database still
 * waking up) is retried once after SESSION_RETRY_DELAY_MS; if that fails
 * too, rejects, and the caller shows the 'unreachable' state. Before this,
 * any failure here was taken as "signed out" and sent the user to login.
 */
async function checkSession(): Promise<User | null> {
  try {
    return await authApi.getCurrentUser()
  } catch (err) {
    if (isSignedOut(err)) return null
  }
  await delay(SESSION_RETRY_DELAY_MS)
  try {
    return await authApi.getCurrentUser()
  } catch (err) {
    if (isSignedOut(err)) return null
    throw err
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  // The session cookie is httpOnly, so there's no way to tell from here
  // whether one exists: always start loading and ask the server.
  const [status, setStatus] = useState<AuthStatus>('loading')
  // Bumped by retry() to run the session check again.
  const [checkCount, setCheckCount] = useState(0)

  const logout = useCallback(() => {
    // Signed out locally right away; the request only clears the cookie.
    // If it fails, the cookie still expires on its own.
    authApi.logout().catch(() => {})
    setUser(null)
    setStatus('unauthenticated')
  }, [])

  // Registered once so a 401 from any authenticated request (expired or
  // invalid session) logs the user out instead of leaving the app stuck.
  useEffect(() => {
    setUnauthorizedHandler(logout)
    return () => setUnauthorizedHandler(null)
  }, [logout])

  useEffect(() => {
    let cancelled = false
    checkSession()
      .then((current) => {
        if (cancelled) return
        if (current) {
          setUser(current)
          setStatus('authenticated')
        } else {
          // No session, or an expired/invalid one (which the server clears
          // in the same 401 response).
          setStatus('unauthenticated')
        }
      })
      .catch(() => {
        // Unknown, not signed out: the cookie may be perfectly valid.
        if (!cancelled) setStatus('unreachable')
      })
    return () => {
      cancelled = true
    }
  }, [checkCount])

  const retry = useCallback(() => {
    setStatus('loading')
    setCheckCount((n) => n + 1)
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const current = await authApi.login(email, password)
    setUser(current)
    setStatus('authenticated')
  }, [])

  const register = useCallback(async (input: RegisterInput) => {
    const current = await authApi.register(input)
    setUser(current)
    setStatus('authenticated')
  }, [])

  const value = useMemo<AuthValue>(
    () => ({ user, status, login, register, logout, retry }),
    [user, status, login, register, logout, retry],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

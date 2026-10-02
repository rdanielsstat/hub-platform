import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { authApi, type RegisterInput, type User } from '@/services/api'
import { setUnauthorizedHandler } from '@/services/api/http'
import { AuthContext, type AuthStatus, type AuthValue } from '@/auth-context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  // The session cookie is httpOnly, so there's no way to tell from here
  // whether one exists: always start loading and ask the server.
  const [status, setStatus] = useState<AuthStatus>('loading')

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
    authApi
      .getCurrentUser()
      .then((current) => {
        setUser(current)
        setStatus('authenticated')
      })
      .catch(() => {
        // No session, or an expired/invalid one (which the server clears
        // in the same 401 response).
        setStatus('unauthenticated')
      })
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
    () => ({ user, status, login, register, logout }),
    [user, status, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

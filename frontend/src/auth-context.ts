import { createContext } from 'react'
import type { RegisterInput, User } from '@/services/api'

/**
 * 'unreachable': the session check got no usable answer (no response, or
 * a 5xx) even after a retry. Whether the user is signed in is unknown, so
 * the app shows a retry screen rather than the login page.
 */
export type AuthStatus =
  'loading' | 'authenticated' | 'unauthenticated' | 'unreachable'

export interface AuthValue {
  user: User | null
  status: AuthStatus
  login: (email: string, password: string) => Promise<void>
  register: (input: RegisterInput) => Promise<void>
  logout: () => void
  /** Run the session check again (from the 'unreachable' screen). */
  retry: () => void
}

export const AuthContext = createContext<AuthValue | null>(null)

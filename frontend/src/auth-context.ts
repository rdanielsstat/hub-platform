import { createContext } from 'react'
import type { RegisterInput, User } from '@/services/api'

export type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated'

export interface AuthValue {
  user: User | null
  status: AuthStatus
  login: (email: string, password: string) => Promise<void>
  register: (input: RegisterInput) => Promise<void>
  logout: () => void
}

export const AuthContext = createContext<AuthValue | null>(null)

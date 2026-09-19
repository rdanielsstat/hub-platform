import { httpRequest } from './http'
import { clearToken, setToken } from './token'
import type { RegisterInput, User } from './types'

interface TokenResponse {
  access_token: string
  token_type: string
}

/**
 * Auth always hits the real backend; there is no mock variant (the
 * frontend never had auth before this).
 */
export const authApi = {
  async register(input: RegisterInput): Promise<User> {
    const token = await httpRequest<TokenResponse>('/auth/register', {
      method: 'POST',
      body: input,
      skipAuth: true,
    })
    setToken(token.access_token)
    return authApi.getCurrentUser()
  },

  async login(email: string, password: string): Promise<User> {
    const token = await httpRequest<TokenResponse>('/auth/login', {
      method: 'POST',
      form: { username: email, password },
      skipAuth: true,
    })
    setToken(token.access_token)
    return authApi.getCurrentUser()
  },

  async getCurrentUser(): Promise<User> {
    return httpRequest<User>('/auth/me')
  },

  logout(): void {
    clearToken()
  },
}

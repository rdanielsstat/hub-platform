import { httpRequest } from './http'
import type { RegisterInput, User } from './types'

/**
 * Auth always hits the real backend; there is no mock variant (the
 * frontend never had auth before this).
 *
 * Register and login set the session as an httpOnly cookie, which the
 * browser stores and sends on its own. Their responses also carry the
 * token in the body for non-browser API clients; the web app ignores it
 * and never stores it.
 */
export const authApi = {
  async register(input: RegisterInput): Promise<User> {
    await httpRequest('/auth/register', {
      method: 'POST',
      body: input,
      ignoreUnauthorized: true,
    })
    return authApi.getCurrentUser()
  },

  async login(email: string, password: string): Promise<User> {
    await httpRequest('/auth/login', {
      method: 'POST',
      form: { username: email, password },
      ignoreUnauthorized: true,
    })
    return authApi.getCurrentUser()
  },

  /** Rejects with a 401 HttpError when there's no valid session. */
  async getCurrentUser(): Promise<User> {
    return httpRequest<User>('/auth/me', { ignoreUnauthorized: true })
  },

  /** Asks the server to clear the cookie (JavaScript can't touch it). */
  async logout(): Promise<void> {
    await httpRequest('/auth/logout', {
      method: 'POST',
      ignoreUnauthorized: true,
    })
  },
}

import { API_BASE_URL } from '@/lib/config'
import { getToken } from './token'

export class HttpError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'HttpError'
    this.status = status
  }
}

type UnauthorizedHandler = () => void

/**
 * Fires when an authenticated request comes back 401 (expired/invalid
 * token) — the app uses this to log the user out and bounce them to
 * login, rather than leaving the UI stuck on a failed request. Not fired
 * for a plain wrong-password 401 from /auth/login itself, since that
 * request never carries a token.
 */
let onUnauthorized: UnauthorizedHandler | null = null

export function setUnauthorizedHandler(
  handler: UnauthorizedHandler | null,
): void {
  onUnauthorized = handler
}

interface RequestOptions {
  method?: string
  body?: unknown
  /** application/x-www-form-urlencoded body, for the OAuth2 login endpoint */
  form?: Record<string, string>
  /** skip attaching the stored bearer token (register/login themselves) */
  skipAuth?: boolean
}

export async function httpRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {}
  let requestBody: BodyInit | undefined

  if (options.form) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    requestBody = new URLSearchParams(options.form).toString()
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    requestBody = JSON.stringify(options.body)
  }

  if (!options.skipAuth) {
    const token = getToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
  }

  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method ?? 'GET',
    headers,
    body: requestBody,
  })

  if (res.status === 401 && headers['Authorization']) {
    onUnauthorized?.()
  }

  if (!res.ok) {
    throw new HttpError(res.status, await extractErrorMessage(res))
  }

  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

async function extractErrorMessage(res: Response): Promise<string> {
  try {
    const data: unknown = await res.json()
    if (data && typeof data === 'object' && 'detail' in data) {
      const detail = (data as { detail: unknown }).detail
      if (typeof detail === 'string') return detail
      if (Array.isArray(detail) && detail.length > 0) {
        const first: unknown = detail[0]
        if (first && typeof first === 'object' && 'msg' in first) {
          const msg = (first as { msg: unknown }).msg
          if (typeof msg === 'string') return msg
        }
      }
    }
  } catch {
    // response wasn't JSON; fall through to status text
  }
  return res.statusText || `Request failed with status ${res.status}`
}

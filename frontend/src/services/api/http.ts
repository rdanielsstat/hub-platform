import { API_BASE_URL } from '@/lib/config'

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
 * Fires when a request comes back 401 (the session cookie expired or is
 * invalid) — the app uses this to log the user out and bounce them to
 * login, rather than leaving the UI stuck on a failed request. Requests
 * made with ignoreUnauthorized never fire it.
 */
let onUnauthorized: UnauthorizedHandler | null = null

export function setUnauthorizedHandler(
  handler: UnauthorizedHandler | null,
): void {
  onUnauthorized = handler
}

/** A request that got no response at all (status 0), or a 5xx. */
export interface RequestFailure {
  method: string
  path: string
  url: string
  status: number
}

type RequestFailureHandler = (failure: RequestFailure) => void

/**
 * Fires for every request that fails on the server's or the network's
 * side: no response (status 0) or a 5xx. Not for 4xx, which are expected
 * answers. lib/error-reporting.ts uses it to report failed calls.
 */
let onRequestFailure: RequestFailureHandler | null = null

export function setRequestFailureHandler(
  handler: RequestFailureHandler | null,
): void {
  onRequestFailure = handler
}

interface RequestOptions {
  method?: string
  body?: unknown
  /** application/x-www-form-urlencoded body, for the OAuth2 login endpoint */
  form?: Record<string, string>
  /**
   * A 401 from this request isn't an expired session: a wrong password
   * on login, or the on-load "am I signed in?" check. Don't fire the
   * unauthorized handler for it.
   */
  ignoreUnauthorized?: boolean
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

  // The session is the httpOnly hub_token cookie, which the browser
  // attaches on its own; this code never sees the token. 'include' (not
  // the default 'same-origin') so it's also sent locally, where the API is
  // on another port. Deployed, CloudFront serves both from one origin.
  const method = options.method ?? 'GET'
  const url = `${API_BASE_URL}${path}`
  let res: Response
  try {
    res = await fetch(url, {
      method,
      headers,
      body: requestBody,
      credentials: 'include',
    })
  } catch (err) {
    // No response at all: offline, DNS, CORS, or the backend unreachable.
    onRequestFailure?.({ method, path, url, status: 0 })
    throw err
  }

  if (res.status >= 500) {
    onRequestFailure?.({ method, path, url, status: res.status })
  }

  if (res.status === 401 && !options.ignoreUnauthorized) {
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

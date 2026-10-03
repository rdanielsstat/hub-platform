import { API_BASE_URL } from '@/lib/config'

/**
 * Frontend error reports, sent to the backend's POST /client-errors, which
 * logs each one as a JSON line (backend/app/routers/errors.py). Wired up by
 * lib/error-reporting.ts; nothing is sent until enableClientErrorReports()
 * runs, which only main.tsx does, so unit tests never send reports.
 *
 * Deliberately plain fetch, not httpRequest: a report that fails must not
 * be reported in turn, and must never trip the 401 logout handler.
 */
export interface ClientErrorReport {
  kind: 'error' | 'unhandledrejection' | 'render' | 'http'
  message: string
  stack?: string
  /** kind 'http': the API URL that failed, its method, and its status (0: no response). */
  endpoint?: string
  method?: string
  status?: number
}

// Per page load. Past this, a crash loop or a dead backend would only add
// noise (and hit the server's per-IP limit anyway).
export const MAX_REPORTS_PER_PAGE = 20

// The server's field limits (ClientErrorReport in openapi.yaml). Truncating
// here keeps a long stack from turning the whole report into a 422.
const MAX_MESSAGE = 2000
const MAX_STACK = 8000
const MAX_URL = 2000
const MAX_USER_AGENT = 500
const MAX_ENDPOINT = 500

let enabled = false
let sent = 0
const seen = new Set<string>()

export function enableClientErrorReports(on = true): void {
  enabled = on
  sent = 0
  seen.clear()
}

function clip(value: string | undefined, max: number): string | undefined {
  return value === undefined ? undefined : value.slice(0, max)
}

/** Fire and forget. Identical reports are sent once per page load. */
export function reportClientError(report: ClientErrorReport): void {
  if (!enabled || sent >= MAX_REPORTS_PER_PAGE) return
  const key = [
    report.kind,
    report.message,
    report.endpoint,
    report.status,
  ].join('|')
  if (seen.has(key)) return
  seen.add(key)
  sent += 1

  const body = {
    ...report,
    message: clip(report.message, MAX_MESSAGE) || '(no message)',
    stack: clip(report.stack, MAX_STACK),
    endpoint: clip(report.endpoint, MAX_ENDPOINT),
    // No query string: the server strips it too, but it needn't leave the browser.
    url: clip(window.location.origin + window.location.pathname, MAX_URL),
    userAgent: clip(navigator.userAgent, MAX_USER_AGENT),
  }
  try {
    fetch(`${API_BASE_URL}/client-errors`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      credentials: 'include',
      // Lets the request finish even if the page is being unloaded.
      keepalive: true,
    }).catch(() => {})
  } catch {
    // Reporting must never throw into the code that hit the error.
  }
}

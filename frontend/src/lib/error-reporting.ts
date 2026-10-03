import {
  enableClientErrorReports,
  reportClientError,
} from '@/services/api/client-errors'
import { setRequestFailureHandler } from '@/services/api/http'

/**
 * Turns on frontend error reporting (see services/api/client-errors.ts).
 * Called once from main.tsx. Covers:
 *  - uncaught errors (window 'error')
 *  - unhandled promise rejections (window 'unhandledrejection')
 *  - failed API calls: no response at all, or a 5xx (http.ts's failure
 *    hook). 4xx responses are the app working as designed (wrong
 *    password, validation, not found) and aren't reported.
 * React render crashes are reported by components/error-boundary.tsx.
 *
 * Returns a function that undoes all of it, for tests.
 */
export function installErrorReporting(): () => void {
  enableClientErrorReports()

  const onError = (event: ErrorEvent) => {
    const error: unknown = event.error
    reportClientError({
      kind: 'error',
      message: event.message || describe(error),
      stack: error instanceof Error ? error.stack : undefined,
    })
  }
  const onRejection = (event: PromiseRejectionEvent) => {
    const reason: unknown = event.reason
    reportClientError({
      kind: 'unhandledrejection',
      message: describe(reason),
      stack: reason instanceof Error ? reason.stack : undefined,
    })
  }

  window.addEventListener('error', onError)
  window.addEventListener('unhandledrejection', onRejection)
  setRequestFailureHandler((failure) => {
    reportClientError({
      kind: 'http',
      message:
        failure.status === 0
          ? `No response from ${failure.method} ${failure.path}`
          : `${failure.method} ${failure.path} returned ${failure.status}`,
      endpoint: failure.url,
      method: failure.method,
      status: failure.status,
    })
  })

  return () => {
    window.removeEventListener('error', onError)
    window.removeEventListener('unhandledrejection', onRejection)
    setRequestFailureHandler(null)
    enableClientErrorReports(false)
  }
}

function describe(value: unknown): string {
  if (value instanceof Error) return `${value.name}: ${value.message}`
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value) ?? String(value)
  } catch {
    return String(value)
  }
}

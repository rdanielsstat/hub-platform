import { HttpError } from '@/services/api'
import { notifyError } from '@/lib/toast'

/**
 * Turns a caught error into a clear, non-technical message. HttpError's
 * message comes from the backend's own curated `detail` string (e.g.
 * "Project not found"), which is already fine to show as-is. Anything
 * else (network failure, CORS, a non-JSON response) gets a generic,
 * friendly fallback instead of a raw technical message.
 */
export function toUserMessage(err: unknown, fallback: string): string {
  if (err instanceof HttpError && err.message) return err.message
  return fallback
}

/**
 * The single place write paths report a failure to the user. Skips
 * a 401: that's already handled globally (see services/api/http.ts's
 * unauthorized handler, wired to logout in auth.tsx) by routing back to
 * login, so toasting it too would just be a confusing second message.
 */
export function reportError(err: unknown, fallback: string): void {
  if (err instanceof HttpError && err.status === 401) return
  notifyError(toUserMessage(err, fallback))
}

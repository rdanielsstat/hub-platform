import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const reportClientError = vi.fn()
const enableClientErrorReports = vi.fn()
vi.mock('@/services/api/client-errors', () => ({
  reportClientError,
  enableClientErrorReports,
}))

const { installErrorReporting } = await import('./error-reporting')
const { httpRequest } = await import('@/services/api/http')

let uninstall: () => void

beforeEach(() => {
  reportClientError.mockClear()
  uninstall = installErrorReporting()
})

afterEach(() => {
  uninstall()
  vi.restoreAllMocks()
})

describe('installErrorReporting', () => {
  it('turns reporting on, and off again on uninstall', () => {
    expect(enableClientErrorReports).toHaveBeenLastCalledWith()
    uninstall()
    expect(enableClientErrorReports).toHaveBeenLastCalledWith(false)
    uninstall = installErrorReporting()
  })

  it('reports uncaught errors', () => {
    const error = new Error('kaboom')
    window.dispatchEvent(
      new ErrorEvent('error', { message: 'Uncaught Error: kaboom', error }),
    )

    expect(reportClientError).toHaveBeenCalledWith({
      kind: 'error',
      message: 'Uncaught Error: kaboom',
      stack: error.stack,
    })
  })

  it('reports unhandled promise rejections', () => {
    const reason = new TypeError('nope')
    const event = new Event('unhandledrejection') as PromiseRejectionEvent
    Object.defineProperty(event, 'reason', { value: reason })
    window.dispatchEvent(event)

    expect(reportClientError).toHaveBeenCalledWith({
      kind: 'unhandledrejection',
      message: 'TypeError: nope',
      stack: reason.stack,
    })
  })

  it('reports rejections with non-Error reasons', () => {
    const event = new Event('unhandledrejection') as PromiseRejectionEvent
    Object.defineProperty(event, 'reason', { value: { code: 42 } })
    window.dispatchEvent(event)

    expect(reportClientError).toHaveBeenCalledWith(
      expect.objectContaining({ message: '{"code":42}' }),
    )
  })

  it('reports API calls that get no response', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(
      new TypeError('Failed to fetch'),
    )

    await expect(httpRequest('/projects')).rejects.toThrow()

    expect(reportClientError).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: 'http',
        message: 'No response from GET /projects',
        method: 'GET',
        status: 0,
      }),
    )
  })

  it('reports 5xx API responses', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response('{}', { status: 502 }),
    )

    await expect(httpRequest('/auth/me')).rejects.toThrow()

    expect(reportClientError).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: 'http',
        message: 'GET /auth/me returned 502',
        status: 502,
      }),
    )
  })

  it('stops listening after uninstall', () => {
    uninstall()
    window.dispatchEvent(new ErrorEvent('error', { message: 'late' }))

    expect(reportClientError).not.toHaveBeenCalled()
    uninstall = installErrorReporting()
  })
})

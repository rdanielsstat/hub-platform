import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
  type MockInstance,
} from 'vitest'
import {
  MAX_REPORTS_PER_PAGE,
  enableClientErrorReports,
  reportClientError,
} from './client-errors'

function sentBodies(
  spy: MockInstance<typeof fetch>,
): Record<string, unknown>[] {
  return spy.mock.calls.map(
    ([, init]) =>
      JSON.parse(String((init as RequestInit).body)) as Record<string, unknown>,
  )
}

let fetchSpy: MockInstance<typeof fetch>

beforeEach(() => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValue(new Response(null, { status: 204 }))
})

afterEach(() => {
  enableClientErrorReports(false)
  vi.restoreAllMocks()
})

describe('reportClientError', () => {
  it('sends nothing until reporting is enabled', () => {
    reportClientError({ kind: 'error', message: 'boom' })

    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('posts the report with the page URL and user agent, keepalive and credentials', () => {
    enableClientErrorReports()

    reportClientError({ kind: 'error', message: 'boom', stack: 'at x' })

    expect(fetchSpy).toHaveBeenCalledTimes(1)
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit]
    expect(url).toMatch(/\/client-errors$/)
    expect(init.method).toBe('POST')
    expect(init.keepalive).toBe(true)
    expect(init.credentials).toBe('include')
    const [body] = sentBodies(fetchSpy)
    expect(body).toMatchObject({
      kind: 'error',
      message: 'boom',
      stack: 'at x',
    })
    expect(body.url).toBe(window.location.origin + window.location.pathname)
    expect(body.userAgent).toBe(navigator.userAgent)
  })

  it('sends an identical report only once per page load', () => {
    enableClientErrorReports()

    reportClientError({ kind: 'error', message: 'same' })
    reportClientError({ kind: 'error', message: 'same' })
    reportClientError({ kind: 'error', message: 'different' })

    expect(fetchSpy).toHaveBeenCalledTimes(2)
  })

  it(`stops after ${MAX_REPORTS_PER_PAGE} reports`, () => {
    enableClientErrorReports()

    for (let i = 0; i < MAX_REPORTS_PER_PAGE + 5; i++) {
      reportClientError({ kind: 'error', message: `error ${i}` })
    }

    expect(fetchSpy).toHaveBeenCalledTimes(MAX_REPORTS_PER_PAGE)
  })

  it("truncates fields to the server's limits", () => {
    enableClientErrorReports()

    reportClientError({
      kind: 'http',
      message: 'm'.repeat(5000),
      stack: 's'.repeat(20000),
      endpoint: 'e'.repeat(1000),
      status: 0,
    })

    const [body] = sentBodies(fetchSpy)
    expect((body.message as string).length).toBe(2000)
    expect((body.stack as string).length).toBe(8000)
    expect((body.endpoint as string).length).toBe(500)
  })

  it('never throws, even when the report itself fails', async () => {
    enableClientErrorReports()
    fetchSpy.mockRejectedValueOnce(new TypeError('Failed to fetch'))

    expect(() =>
      reportClientError({ kind: 'error', message: 'x' }),
    ).not.toThrow()
    await Promise.resolve()
  })
})

import { afterEach, describe, expect, it, vi } from 'vitest'

async function loadApiBaseUrl(): Promise<string> {
  vi.resetModules()
  const { API_BASE_URL } = await import('./config')
  return API_BASE_URL
}

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('API_BASE_URL', () => {
  it('defaults to same-origin /api when VITE_API_BASE_URL is absent', async () => {
    vi.stubEnv('VITE_API_BASE_URL', undefined)

    expect(await loadApiBaseUrl()).toBe('/api')
  })

  it('falls back to /api when VITE_API_BASE_URL is set but empty', async () => {
    vi.stubEnv('VITE_API_BASE_URL', '')

    expect(await loadApiBaseUrl()).toBe('/api')
  })

  it('uses VITE_API_BASE_URL when set', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://localhost:8000')

    expect(await loadApiBaseUrl()).toBe('http://localhost:8000')
  })
})

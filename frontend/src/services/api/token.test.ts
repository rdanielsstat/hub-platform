// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { clearToken, getToken, setToken } from './token'

const STORAGE_KEY = 'hub.token'

describe('token storage round-trip', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('returns null when nothing is stored', () => {
    expect(getToken()).toBeNull()
  })

  it('set then get returns the stored token', () => {
    setToken('abc123')
    expect(getToken()).toBe('abc123')
    expect(localStorage.getItem(STORAGE_KEY)).toBe('abc123')
  })

  it('clear removes the stored token', () => {
    setToken('abc123')
    clearToken()
    expect(getToken()).toBeNull()
  })
})

describe('graceful degradation when storage throws', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('getToken returns null instead of throwing', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('storage disabled')
    })
    expect(() => getToken()).not.toThrow()
    expect(getToken()).toBeNull()
  })

  it('setToken does not throw', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('storage disabled')
    })
    expect(() => setToken('abc123')).not.toThrow()
  })

  it('clearToken does not throw', () => {
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('storage disabled')
    })
    expect(() => clearToken()).not.toThrow()
  })
})

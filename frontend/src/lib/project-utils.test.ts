import { describe, expect, it } from 'vitest'
import type { Project, Status } from '@/services/api'
import { isQuickWin, isStale } from './project-utils'

const NOW = new Date('2026-09-20T00:00:00Z')

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    name: 'Test project',
    pitch: '',
    description: '',
    status: 'Active',
    tags: [],
    excitement: 3,
    effort: 3,
    potential: 3,
    nextAction: '',
    targetDate: null,
    links: [],
    createdAt: NOW.toISOString(),
    updatedAt: NOW.toISOString(),
    ...overrides,
  }
}

describe('isQuickWin', () => {
  it('is true at the excitement/effort thresholds (excitement 4, effort 2)', () => {
    expect(isQuickWin(project({ excitement: 4, effort: 2 }))).toBe(true)
  })

  it('is true comfortably past the thresholds (excitement 5, effort 1)', () => {
    expect(isQuickWin(project({ excitement: 5, effort: 1 }))).toBe(true)
  })

  it('is false just below the excitement threshold', () => {
    expect(isQuickWin(project({ excitement: 3, effort: 2 }))).toBe(false)
  })

  it('is false just above the effort threshold', () => {
    expect(isQuickWin(project({ excitement: 4, effort: 3 }))).toBe(false)
  })

  it.each<Status>(['Parked', 'Graduated', 'Killed'])(
    'is false for closed status %s even when excitement/effort qualify',
    (status) => {
      expect(isQuickWin(project({ status, excitement: 5, effort: 1 }))).toBe(
        false,
      )
    },
  )

  it.each<Status>(['Inbox', 'Exploring', 'Active'])(
    'is true for open status %s when excitement/effort qualify',
    (status) => {
      expect(isQuickWin(project({ status, excitement: 5, effort: 1 }))).toBe(
        true,
      )
    },
  )
})

describe('isStale', () => {
  it('is false just under the 30-day boundary', () => {
    const updatedAt = new Date(NOW.getTime() - 29 * 86400000).toISOString()
    expect(isStale(project({ status: 'Active', updatedAt }), NOW)).toBe(false)
  })

  it('is true exactly at the 30-day boundary', () => {
    const updatedAt = new Date(NOW.getTime() - 30 * 86400000).toISOString()
    expect(isStale(project({ status: 'Active', updatedAt }), NOW)).toBe(true)
  })

  it('is true well past the 30-day boundary', () => {
    const updatedAt = new Date(NOW.getTime() - 90 * 86400000).toISOString()
    expect(isStale(project({ status: 'Exploring', updatedAt }), NOW)).toBe(true)
  })

  it.each<Status>(['Inbox', 'Parked', 'Killed', 'Graduated'])(
    'is false for %s even when far past the 30-day boundary',
    (status) => {
      const updatedAt = new Date(NOW.getTime() - 90 * 86400000).toISOString()
      expect(isStale(project({ status, updatedAt }), NOW)).toBe(false)
    },
  )
})

describe('isQuickWin and isStale together', () => {
  it('a project can be both quick-win and stale', () => {
    const updatedAt = new Date(NOW.getTime() - 45 * 86400000).toISOString()
    const p = project({
      status: 'Active',
      excitement: 5,
      effort: 1,
      updatedAt,
    })
    expect(isQuickWin(p)).toBe(true)
    expect(isStale(p, NOW)).toBe(true)
  })

  it('a project can be neither', () => {
    const p = project({
      status: 'Active',
      excitement: 3,
      effort: 3,
      updatedAt: NOW.toISOString(),
    })
    expect(isQuickWin(p)).toBe(false)
    expect(isStale(p, NOW)).toBe(false)
  })
})

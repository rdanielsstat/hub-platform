import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'
import type { Project, Status } from '@/services/api'
import {
  daysUntil,
  formatDate,
  formatRelative,
  isQuickWin,
  isStale,
  opportunityScore,
} from './project-utils'

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

describe('opportunityScore', () => {
  it('is excitement + potential - effort', () => {
    expect(
      opportunityScore(project({ excitement: 5, potential: 4, effort: 2 })),
    ).toBe(7)
  })

  it('can be negative when effort dominates', () => {
    expect(
      opportunityScore(project({ excitement: 1, potential: 1, effort: 5 })),
    ).toBe(-3)
  })
})

describe('daysUntil', () => {
  it('returns null for a null input', () => {
    expect(daysUntil(null)).toBeNull()
  })

  it('is positive for a future date-only string', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-20T12:00:00Z'))
    expect(daysUntil('2026-09-25')).toBe(5)
    vi.useRealTimers()
  })

  it('is negative for a past date-only string', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-20T12:00:00Z'))
    expect(daysUntil('2026-09-15')).toBe(-5)
    vi.useRealTimers()
  })

  it('is 0 for today (date-only, before local midnight has passed)', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-20T00:00:00'))
    expect(daysUntil('2026-09-20')).toBe(0)
    vi.useRealTimers()
  })
})

describe('formatRelative', () => {
  it('is "just now" for a timestamp under a minute old', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-20T00:00:10Z'))
    expect(formatRelative('2026-09-20T00:00:00Z')).toBe('just now')
    vi.useRealTimers()
  })

  it('formats minutes ago', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-20T00:10:00Z'))
    expect(formatRelative('2026-09-20T00:00:00Z')).toBe('10m ago')
    vi.useRealTimers()
  })

  it('formats hours ago', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-20T05:00:00Z'))
    expect(formatRelative('2026-09-20T00:00:00Z')).toBe('5h ago')
    vi.useRealTimers()
  })

  it('formats days ago', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-25T00:00:00Z'))
    expect(formatRelative('2026-09-20T00:00:00Z')).toBe('5d ago')
    vi.useRealTimers()
  })

  it('formats months ago', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-19T00:00:00Z'))
    expect(formatRelative('2026-09-20T00:00:00Z')).toBe('2mo ago')
    vi.useRealTimers()
  })

  it('formats years ago', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2028-09-20T00:00:00Z'))
    expect(formatRelative('2026-09-20T00:00:00Z')).toBe('2y ago')
    vi.useRealTimers()
  })
})

describe('formatDate', () => {
  const originalTz = process.env.TZ

  beforeAll(() => {
    process.env.TZ = 'UTC'
  })

  afterAll(() => {
    process.env.TZ = originalTz
  })

  it('formats a date-only string at local midnight, not shifted by UTC parsing', () => {
    expect(formatDate('2026-09-01')).toBe('Sep 1, 2026')
  })

  it('formats a full ISO timestamp as an absolute instant', () => {
    expect(formatDate('2026-09-01T00:00:00Z')).toBe('Sep 1, 2026')
  })
})

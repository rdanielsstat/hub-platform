import type { Project, Status } from '@/services/api'

/** Tailwind class sets for each status pill. */
export const statusStyles: Record<Status, string> = {
  Inbox: 'bg-slate-100 text-slate-700 dark:bg-slate-500/15 dark:text-slate-300',
  Exploring: 'bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300',
  Active:
    'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300',
  Parked:
    'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300',
  Graduated:
    'bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300',
  Killed: 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300',
}

export const statusDot: Record<Status, string> = {
  Inbox: 'bg-slate-400',
  Exploring: 'bg-sky-500',
  Active: 'bg-emerald-500',
  Parked: 'bg-amber-500',
  Graduated: 'bg-violet-500',
  Killed: 'bg-rose-500',
}

export function formatRelative(iso: string): string {
  const then = new Date(iso).getTime()
  const diff = Date.now() - then
  const mins = Math.round(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  if (days < 30) return `${days}d ago`
  const months = Math.round(days / 30)
  if (months < 12) return `${months}mo ago`
  return `${Math.round(months / 12)}y ago`
}

/** Parses a date-only ("YYYY-MM-DD") string as local midnight instead of UTC. */
function parseDateOnly(iso: string): Date {
  return iso.includes('T') ? new Date(iso) : new Date(`${iso}T00:00:00`)
}

export function formatDate(iso: string): string {
  return parseDateOnly(iso).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

export function daysUntil(iso: string | null): number | null {
  if (!iso) return null
  const target = parseDateOnly(iso).getTime()
  return Math.ceil((target - Date.now()) / (24 * 60 * 60 * 1000))
}

/** Higher = better opportunity: exciting + high potential, low effort. */
export function opportunityScore(p: Project): number {
  return p.excitement + p.potential - p.effort
}

const QUICK_WIN_STATUSES: Status[] = ['Inbox', 'Exploring', 'Active']
const STALE_STATUSES: Status[] = ['Active', 'Exploring']
const STALE_THRESHOLD_DAYS = 30

/** High-excitement, low-effort, and still an open idea worth grabbing. */
export function isQuickWin(p: Project): boolean {
  return (
    QUICK_WIN_STATUSES.includes(p.status) && p.excitement >= 4 && p.effort <= 2
  )
}

/** Hasn't moved in 30+ days, in a status where that's supposed to be rare. */
export function isStale(p: Project, now: Date = new Date()): boolean {
  if (!STALE_STATUSES.includes(p.status)) return false
  const ageDays = (now.getTime() - new Date(p.updatedAt).getTime()) / 86400000
  return ageDays >= STALE_THRESHOLD_DAYS
}

/**
 * Whether a link URL is safe to render as an <a href>: only http(s).
 * The backend already rejects anything else on write; this is the second
 * line, so a javascript:, data: or file: URL that got into the database
 * some other way still never becomes a clickable link.
 */
export function isSafeLinkUrl(url: string): boolean {
  return /^https?:\/\//i.test(url)
}

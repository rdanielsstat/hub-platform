import { useMemo, useState } from 'react'
import { AlertTriangle, Inbox, Plus } from 'lucide-react'
import { useStore } from '@/use-store'
import type { Status } from '@/services/api'
import { ProjectCard } from '@/components/project-card'
import { StatsRow } from '@/components/dashboard/stats-row'
import { DashboardToolbar } from '@/components/dashboard/dashboard-toolbar'
import type { SortKey } from '@/components/dashboard/sort-options'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/empty-state'
import { daysUntil, opportunityScore } from '@/lib/project-utils'

export function DashboardPage({ onCapture }: { onCapture: () => void }) {
  const { projects, loading, error, refresh } = useStore()
  const [status, setStatus] = useState<Status | 'all'>('all')
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<SortKey>('updated')
  const [tag, setTag] = useState<string | null>(null)

  const allTags = useMemo(() => {
    const set = new Set<string>()
    projects.forEach((p) => p.tags.forEach((t) => set.add(t)))
    return [...set].sort()
  }, [projects])

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    const filtered = projects.filter((p) => {
      if (status !== 'all' && p.status !== status) return false
      if (tag && !p.tags.includes(tag)) return false
      if (!q) return true
      return (
        p.name.toLowerCase().includes(q) ||
        p.pitch.toLowerCase().includes(q) ||
        p.description.toLowerCase().includes(q) ||
        p.tags.some((t) => t.includes(q))
      )
    })

    const sorted = [...filtered]
    sorted.sort((a, b) => {
      switch (sort) {
        case 'opportunity':
          return opportunityScore(b) - opportunityScore(a)
        case 'excitement':
          return b.excitement - a.excitement
        case 'effort':
          return a.effort - b.effort
        case 'name':
          return a.name.localeCompare(b.name)
        case 'target': {
          const da = daysUntil(a.targetDate)
          const db = daysUntil(b.targetDate)
          if (da === null && db === null) return 0
          if (da === null) return 1
          if (db === null) return -1
          return da - db
        }
        case 'updated':
        default:
          return b.updatedAt.localeCompare(a.updatedAt)
      }
    })
    return sorted
  }, [projects, status, tag, query, sort])

  return (
    <div>
      <div className="mb-6 flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Ideas</h1>
        <p className="text-sm text-muted-foreground">
          Everything captured. Parked, held, or on its way to a build.
        </p>
      </div>

      {error ? null : (
        <div className="mb-5 flex flex-col gap-4">
          <StatsRow
            projects={projects}
            activeStatus={status}
            onSelect={setStatus}
          />
          <DashboardToolbar
            query={query}
            onQuery={setQuery}
            sort={sort}
            onSort={setSort}
            tags={allTags}
            activeTag={tag}
            onTag={setTag}
          />
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="h-44 animate-pulse rounded-xl border border-border bg-muted/40"
            />
          ))}
        </div>
      ) : error ? (
        <EmptyState
          icon={AlertTriangle}
          tone="danger"
          title="Couldn't load your ideas"
          message={error}
          action={
            <Button variant="outline" size="lg" onClick={() => void refresh()}>
              Try again
            </Button>
          }
        />
      ) : visible.length === 0 ? (
        <EmptyState
          icon={Inbox}
          title={projects.length > 0 ? 'No matches' : 'Nothing captured yet'}
          message={
            projects.length > 0
              ? 'Try clearing filters or search.'
              : 'Capture your first idea to get started.'
          }
          action={
            projects.length > 0 ? (
              <Button
                variant="outline"
                size="lg"
                onClick={() => {
                  setStatus('all')
                  setQuery('')
                  setTag(null)
                }}
              >
                Clear filters
              </Button>
            ) : (
              <Button size="lg" onClick={onCapture}>
                <Plus />
                Quick capture
              </Button>
            )
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {visible.map((p) => (
            <ProjectCard key={p.id} project={p} />
          ))}
        </div>
      )}
    </div>
  )
}

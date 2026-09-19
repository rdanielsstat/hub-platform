import { useMemo, useState } from 'react'
import { Inbox, Plus } from 'lucide-react'
import { useStore } from '@/use-store'
import type { Status } from '@/services/api'
import { ProjectCard } from '@/components/project-card'
import { StatsRow } from '@/components/dashboard/stats-row'
import { DashboardToolbar } from '@/components/dashboard/dashboard-toolbar'
import type { SortKey } from '@/components/dashboard/sort-options'
import { Button } from '@/components/ui/button'
import { daysUntil, opportunityScore } from '@/lib/project-utils'

export function DashboardPage({ onCapture }: { onCapture: () => void }) {
  const { projects, loading } = useStore()
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

      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="h-44 animate-pulse rounded-xl border border-border bg-muted/40"
            />
          ))}
        </div>
      ) : visible.length === 0 ? (
        <EmptyState
          hasProjects={projects.length > 0}
          onCapture={onCapture}
          onReset={() => {
            setStatus('all')
            setQuery('')
            setTag(null)
          }}
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

function EmptyState({
  hasProjects,
  onCapture,
  onReset,
}: {
  hasProjects: boolean
  onCapture: () => void
  onReset: () => void
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 rounded-xl border border-dashed border-border py-20 text-center">
      <div className="grid size-12 place-items-center rounded-2xl bg-muted text-muted-foreground">
        <Inbox className="size-6" />
      </div>
      <div className="space-y-1">
        <h2 className="font-semibold">
          {hasProjects ? 'No matches' : 'Nothing captured yet'}
        </h2>
        <p className="text-sm text-muted-foreground">
          {hasProjects
            ? 'Try clearing filters or search.'
            : 'Capture your first idea to get started.'}
        </p>
      </div>
      {hasProjects ? (
        <Button variant="outline" size="lg" onClick={onReset}>
          Clear filters
        </Button>
      ) : (
        <Button size="lg" onClick={onCapture}>
          <Plus />
          Quick capture
        </Button>
      )}
    </div>
  )
}

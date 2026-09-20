import type { Project, Status } from '@/services/api'
import { statusDot } from '@/lib/project-utils'
import { cn } from '@/lib/utils'

export function StatsRow({
  projects,
  activeStatus,
  onSelect,
}: {
  projects: Project[]
  activeStatus: Status | 'all'
  onSelect: (status: Status | 'all') => void
}) {
  const counts = projects.reduce<Record<string, number>>((acc, p) => {
    acc[p.status] = (acc[p.status] ?? 0) + 1
    return acc
  }, {})

  const order: (Status | 'all')[] = [
    'all',
    'Inbox',
    'Exploring',
    'Active',
    'Parked',
    'Graduated',
    'Killed',
  ]

  return (
    <div className="flex flex-wrap gap-2">
      {order.map((key) => {
        const count = key === 'all' ? projects.length : (counts[key] ?? 0)
        const active = activeStatus === key
        return (
          <button
            key={key}
            type="button"
            onClick={() => onSelect(key)}
            aria-pressed={active}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors',
              active
                ? 'border-foreground bg-foreground text-background'
                : 'border-border bg-card text-muted-foreground hover:bg-muted hover:text-foreground',
            )}
          >
            {key !== 'all' ? (
              <span
                className={cn(
                  'size-1.5 rounded-full',
                  statusDot[key as Status],
                )}
              />
            ) : null}
            {key === 'all' ? 'All' : key}
            <span
              className={cn(
                'tabular-nums',
                active ? 'text-background/70' : 'text-muted-foreground/60',
              )}
            >
              {count}
            </span>
          </button>
        )
      })}
    </div>
  )
}

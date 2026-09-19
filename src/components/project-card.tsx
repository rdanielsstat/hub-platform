import { Link } from 'react-router-dom'
import { ArrowUpRight, CalendarClock, Target, Zap } from 'lucide-react'
import type { Project } from '@/services/api'
import { StatusBadge } from '@/components/status-badge'
import {
  daysUntil,
  formatRelative,
  opportunityScore,
} from '@/lib/project-utils'
import { cn } from '@/lib/utils'

export function ProjectCard({ project }: { project: Project }) {
  const due = daysUntil(project.targetDate)
  const score = opportunityScore(project)

  return (
    <Link
      to={`/project/${project.id}`}
      className="group flex flex-col gap-3 rounded-xl border border-border bg-card p-4 shadow-sm transition-all hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-3">
        <StatusBadge status={project.status} />
        <ArrowUpRight className="size-4 shrink-0 text-muted-foreground/50 transition-colors group-hover:text-primary" />
      </div>

      <div className="flex flex-col gap-1">
        <h3 className="font-semibold leading-snug tracking-tight">
          {project.name}
        </h3>
        <p className="line-clamp-2 text-sm text-muted-foreground">
          {project.pitch || project.description || 'No pitch yet.'}
        </p>
      </div>

      {project.tags.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {project.tags.slice(0, 4).map((tag) => (
            <span
              key={tag}
              className="rounded-md bg-muted px-1.5 py-0.5 text-[0.7rem] font-medium text-muted-foreground"
            >
              {tag}
            </span>
          ))}
        </div>
      ) : null}

      <div className="mt-auto flex items-center justify-between gap-2 border-t border-border/70 pt-3 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1" title="Excitement">
          <Zap className="size-3.5 text-primary" />
          {project.excitement}
        </span>
        <span className="inline-flex items-center gap-1" title="Potential">
          <Target className="size-3.5 text-emerald-500" />
          {project.potential}
        </span>
        <span
          className="inline-flex items-center gap-1"
          title="Opportunity score (excitement + potential − effort)"
        >
          <span className="font-medium text-foreground tabular-nums">
            {score > 0 ? `+${score}` : score}
          </span>
        </span>
        {due !== null ? (
          <span
            className={cn(
              'inline-flex items-center gap-1',
              due < 0
                ? 'text-rose-500'
                : due <= 7
                  ? 'text-amber-600 dark:text-amber-400'
                  : '',
            )}
          >
            <CalendarClock className="size-3.5" />
            {due < 0 ? `${Math.abs(due)}d over` : `${due}d`}
          </span>
        ) : (
          <span className="text-muted-foreground/70">
            {formatRelative(project.updatedAt)}
          </span>
        )}
      </div>
    </Link>
  )
}

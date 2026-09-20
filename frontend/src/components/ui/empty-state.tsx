import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface EmptyStateProps {
  icon: LucideIcon
  title: string
  message?: ReactNode
  action?: ReactNode
  tone?: 'neutral' | 'danger'
  /**
   * 'page': this *is* the page's content (not-found, project-detail's
   * not-found/load-error branches) — larger title, no surrounding box.
   * 'panel': a section embedded in a page that already has its own
   * heading (dashboard's empty/load-error states) — smaller title,
   * dashed-border box.
   */
  variant?: 'page' | 'panel'
}

export function EmptyState({
  icon: Icon,
  title,
  message,
  action,
  tone = 'neutral',
  variant = 'panel',
}: EmptyStateProps) {
  const Heading = variant === 'page' ? 'h1' : 'h2'

  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-4 text-center',
        variant === 'panel'
          ? cn(
              'rounded-xl border border-dashed py-20',
              tone === 'danger'
                ? 'border-rose-500/30 bg-rose-500/5'
                : 'border-border',
            )
          : 'py-24',
      )}
    >
      <div
        className={cn(
          'grid size-12 place-items-center rounded-2xl',
          tone === 'danger'
            ? 'bg-rose-500/10 text-rose-500'
            : 'bg-muted text-muted-foreground',
        )}
      >
        <Icon className="size-6" />
      </div>
      <div className="space-y-1">
        <Heading
          className={cn('font-semibold', variant === 'page' && 'text-lg')}
        >
          {title}
        </Heading>
        {message ? (
          <p className="text-sm text-muted-foreground">{message}</p>
        ) : null}
      </div>
      {action}
    </div>
  )
}

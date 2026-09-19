import type { Status } from '@/services/api'
import { statusStyles, statusDot } from '@/lib/project-utils'
import { cn } from '@/lib/utils'

export function StatusBadge({
  status,
  className,
}: {
  status: Status
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium',
        statusStyles[status],
        className,
      )}
    >
      <span className={cn('size-1.5 rounded-full', statusDot[status])} />
      {status}
    </span>
  )
}

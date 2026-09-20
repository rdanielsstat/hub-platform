import { cn } from '@/lib/utils'

/** Same pill shape as StatusBadge, for the quick-win/stale indicators. */
export function IndicatorBadge({
  label,
  dotClassName,
  className,
}: {
  label: string
  dotClassName: string
  className: string
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium',
        className,
      )}
    >
      <span className={cn('size-1.5 rounded-full', dotClassName)} />
      {label}
    </span>
  )
}

import { cn } from '@/lib/utils'

export function RatingInput({
  label,
  value,
  onChange,
  accent = 'bg-foreground',
}: {
  label: string
  value: number
  onChange: (value: number) => void
  accent?: string
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">
          {label}
        </span>
        <span className="text-xs tabular-nums text-muted-foreground">
          {value}/5
        </span>
      </div>
      <div className="flex gap-1">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            aria-label={`${label}: ${n}`}
            onClick={() => onChange(n)}
            className={cn(
              'h-2 flex-1 rounded-full transition-colors',
              n <= value ? accent : 'bg-muted hover:bg-muted-foreground/30',
            )}
          />
        ))}
      </div>
    </div>
  )
}

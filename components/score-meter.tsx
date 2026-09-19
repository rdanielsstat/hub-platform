import { cn } from '@/lib/utils'

const tones = {
  excitement: 'bg-primary',
  potential: 'bg-emerald-500',
  effort: 'bg-amber-500',
} as const

export function ScoreMeter({
  label,
  value,
  tone,
}: {
  label: string
  value: number
  tone: keyof typeof tones
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium tabular-nums">{value}/5</span>
      </div>
      <div className="flex gap-1">
        {[1, 2, 3, 4, 5].map((n) => (
          <span
            key={n}
            className={cn(
              'h-1.5 flex-1 rounded-full',
              n <= value ? tones[tone] : 'bg-muted',
            )}
          />
        ))}
      </div>
    </div>
  )
}

/** Editable 1–5 selector used in forms. */
export function ScorePicker({
  label,
  value,
  onChange,
  tone,
}: {
  label: string
  value: number
  onChange: (value: number) => void
  tone: keyof typeof tones
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <div className="flex gap-1.5">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => onChange(n)}
            aria-label={`${label} ${n} of 5`}
            aria-pressed={n <= value}
            className={cn(
              'h-6 flex-1 rounded-md border transition-colors',
              n <= value
                ? cn(tones[tone], 'border-transparent')
                : 'border-border bg-muted/40 hover:bg-muted',
            )}
          />
        ))}
      </div>
    </div>
  )
}

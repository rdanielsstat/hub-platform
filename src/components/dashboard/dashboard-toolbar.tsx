import { Search, X } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { SORT_LABELS, type SortKey } from '@/components/dashboard/sort-options'

export function DashboardToolbar({
  query,
  onQuery,
  sort,
  onSort,
  tags,
  activeTag,
  onTag,
}: {
  query: string
  onQuery: (value: string) => void
  sort: SortKey
  onSort: (value: SortKey) => void
  tags: string[]
  activeTag: string | null
  onTag: (tag: string | null) => void
}) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => onQuery(e.target.value)}
            placeholder="Search ideas, pitches, tags…"
            className="h-9 pl-9"
          />
          {query ? (
            <button
              type="button"
              onClick={() => onQuery('')}
              aria-label="Clear search"
              className="absolute right-2 top-1/2 grid size-6 -translate-y-1/2 place-items-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <X className="size-3.5" />
            </button>
          ) : null}
        </div>
        <Select
          value={sort}
          onChange={(e) => onSort(e.target.value as SortKey)}
          className="h-9 sm:w-52"
          aria-label="Sort projects"
        >
          {(Object.keys(SORT_LABELS) as SortKey[]).map((key) => (
            <option key={key} value={key}>
              {SORT_LABELS[key]}
            </option>
          ))}
        </Select>
      </div>

      {tags.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1.5">
          {tags.map((tag) => {
            const active = activeTag === tag
            return (
              <button
                key={tag}
                type="button"
                onClick={() => onTag(active ? null : tag)}
                className={cn(
                  'rounded-md px-2 py-0.5 text-xs font-medium transition-colors',
                  active
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-muted-foreground hover:text-foreground',
                )}
              >
                #{tag}
              </button>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}

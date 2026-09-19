export type SortKey =
  'updated' | 'opportunity' | 'excitement' | 'effort' | 'target' | 'name'

export const SORT_LABELS: Record<SortKey, string> = {
  updated: 'Recently updated',
  opportunity: 'Opportunity score',
  excitement: 'Excitement',
  effort: 'Lowest effort',
  target: 'Target date',
  name: 'Name (A–Z)',
}

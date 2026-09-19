export const STATUSES = [
  'Inbox',
  'Exploring',
  'Active',
  'Parked',
  'Graduated',
  'Killed',
] as const

export type Status = (typeof STATUSES)[number]

export interface Link {
  label?: string
  url: string
}

export interface Project {
  id: string
  name: string
  /** one-line, scannable pitch, separate from description */
  pitch: string
  /** the full brain-dump */
  description: string
  status: Status
  tags: string[]
  excitement: number // 1–5
  effort: number // 1–5
  potential: number // 1–5
  /** the single next concrete step (GTD core) */
  nextAction: string
  /** ISO date string or null */
  targetDate: string | null
  links: Link[]
  createdAt: string
  updatedAt: string
}

export interface Note {
  id: string
  projectId: string
  body: string
  createdAt: string
}

export interface CreateProjectInput {
  name: string
  pitch?: string
  description?: string
  status?: Status
  tags?: string[]
  excitement?: number
  effort?: number
  potential?: number
  nextAction?: string
  targetDate?: string | null
  links?: Link[]
}

export type UpdateProjectInput = Partial<Omit<Project, 'id' | 'createdAt'>>

export interface User {
  id: string
  email: string
  displayName: string | null
  createdAt: string
  updatedAt: string
}

export interface RegisterInput {
  email: string
  password: string
  displayName?: string
}

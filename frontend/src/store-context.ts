import { createContext } from 'react'
import type {
  CreateProjectInput,
  Note,
  Project,
  UpdateProjectInput,
} from '@/services/api'

export interface StoreValue {
  projects: Project[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  getProject: (id: string) => Project | undefined
  createProject: (input: CreateProjectInput) => Promise<Project>
  updateProject: (id: string, patch: UpdateProjectInput) => Promise<Project>
  deleteProject: (id: string) => Promise<void>
  addNote: (projectId: string, body: string) => Promise<Note>
  deleteNote: (id: string) => Promise<void>
}

export const StoreContext = createContext<StoreValue | null>(null)

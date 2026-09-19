import { mockApi } from './mock'

/**
 * The single API layer. Every component/store imports from here and never
 * calls `fetch` directly. Today it points at the in-memory mock; to wire a
 * real FastAPI backend later, implement the same surface (see `ApiClient`)
 * and swap the assignment below. No component changes required.
 */
export interface ApiClient {
  listProjects: typeof mockApi.listProjects
  getProject: typeof mockApi.getProject
  createProject: typeof mockApi.createProject
  updateProject: typeof mockApi.updateProject
  deleteProject: typeof mockApi.deleteProject
  listNotes: typeof mockApi.listNotes
  addNote: typeof mockApi.addNote
  deleteNote: typeof mockApi.deleteNote
}

export const api: ApiClient = mockApi

export * from './types'

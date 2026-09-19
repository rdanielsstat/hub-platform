import { mockApi } from './mock'
import { realProjectsApi } from './real'

/**
 * The single API layer. Every component/store imports from here and never
 * calls `fetch` directly.
 *
 * REAL: projects (and auth, via `authApi` below) hit the FastAPI backend
 * over HTTP — see real.ts / auth.ts / http.ts.
 *
 * MOCK — PENDING BACKEND: notes and attachments have no backend yet, so
 * they still run against the in-memory mock (mock.ts). That's the next
 * seam to swap; when it lands, replace the two lines below the same way
 * the project methods were replaced here.
 */
export interface ApiClient {
  listProjects: typeof realProjectsApi.listProjects
  getProject: typeof realProjectsApi.getProject
  createProject: typeof realProjectsApi.createProject
  updateProject: typeof realProjectsApi.updateProject
  deleteProject: typeof realProjectsApi.deleteProject
  listNotes: typeof mockApi.listNotes
  addNote: typeof mockApi.addNote
  deleteNote: typeof mockApi.deleteNote
}

export const api: ApiClient = {
  listProjects: realProjectsApi.listProjects,
  getProject: realProjectsApi.getProject,
  createProject: realProjectsApi.createProject,
  updateProject: realProjectsApi.updateProject,
  deleteProject: realProjectsApi.deleteProject,

  // MOCK — PENDING BACKEND
  listNotes: mockApi.listNotes,
  addNote: mockApi.addNote,
  deleteNote: mockApi.deleteNote,
}

export { authApi } from './auth'
export { HttpError } from './http'
export * from './types'

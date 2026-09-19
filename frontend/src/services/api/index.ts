import { realNotesApi, realProjectsApi } from './real'

/**
 * The single API layer. Every component/store imports from here and never
 * calls `fetch` directly.
 *
 * Projects, notes, and auth (via `authApi` below) all hit the real FastAPI
 * backend over HTTP — see real.ts / auth.ts / http.ts. Attachments are the
 * only piece still pending a backend; there's no frontend type or UI for
 * them yet, so there's nothing to wire here until that's built.
 */
export interface ApiClient {
  listProjects: typeof realProjectsApi.listProjects
  getProject: typeof realProjectsApi.getProject
  createProject: typeof realProjectsApi.createProject
  updateProject: typeof realProjectsApi.updateProject
  deleteProject: typeof realProjectsApi.deleteProject
  listNotes: typeof realNotesApi.listNotes
  addNote: typeof realNotesApi.addNote
  deleteNote: typeof realNotesApi.deleteNote
}

export const api: ApiClient = {
  ...realProjectsApi,
  ...realNotesApi,
}

export { authApi } from './auth'
export { HttpError } from './http'
export * from './types'

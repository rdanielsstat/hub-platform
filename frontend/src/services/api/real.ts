import { HttpError, httpRequest } from './http'
import type {
  CreateProjectInput,
  Note,
  Project,
  UpdateProjectInput,
} from './types'

/** Real HTTP implementation of the project endpoints, against the FastAPI backend. */
export const realProjectsApi = {
  async listProjects(): Promise<Project[]> {
    return httpRequest<Project[]>('/projects')
  },

  async getProject(id: string): Promise<Project | null> {
    try {
      return await httpRequest<Project>(`/projects/${id}`)
    } catch (err) {
      if (err instanceof HttpError && err.status === 404) return null
      throw err
    }
  },

  async createProject(input: CreateProjectInput): Promise<Project> {
    return httpRequest<Project>('/projects', { method: 'POST', body: input })
  },

  async updateProject(id: string, patch: UpdateProjectInput): Promise<Project> {
    return httpRequest<Project>(`/projects/${id}`, {
      method: 'PATCH',
      body: patch,
    })
  },

  async deleteProject(id: string): Promise<void> {
    await httpRequest<void>(`/projects/${id}`, { method: 'DELETE' })
  },
}

/** Real HTTP implementation of the note endpoints, against the FastAPI backend. */
export const realNotesApi = {
  async listNotes(projectId: string): Promise<Note[]> {
    return httpRequest<Note[]>(`/projects/${projectId}/notes`)
  },

  async addNote(
    projectId: string,
    body: string,
  ): Promise<{ note: Note; project: Project }> {
    return httpRequest<{ note: Note; project: Project }>(
      `/projects/${projectId}/notes`,
      { method: 'POST', body: { body } },
    )
  },

  async deleteNote(id: string): Promise<Project> {
    return httpRequest<Project>(`/notes/${id}`, { method: 'DELETE' })
  },
}

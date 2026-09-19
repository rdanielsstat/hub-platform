import { HttpError, httpRequest } from './http'
import type { CreateProjectInput, Project, UpdateProjectInput } from './types'

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

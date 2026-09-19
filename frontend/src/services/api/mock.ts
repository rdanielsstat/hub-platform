import { seedNotes, seedProjects } from './seed'
import type {
  CreateProjectInput,
  Note,
  Project,
  UpdateProjectInput,
} from './types'

/**
 * In-memory mock backend. Holds a mutable copy of the seed data so the whole
 * app runs with no real backend. This is the ONLY place that "owns" the data;
 * swap this module for real HTTP calls behind the same `api` surface later.
 */

let projects: Project[] = seedProjects.map((p) => ({ ...p }))
let notes: Note[] = seedNotes.map((n) => ({ ...n }))

const LATENCY = 220

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), LATENCY))
}

function uid(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`
}

function clone<T>(value: T): T {
  return structuredClone(value)
}

/**
 * Bumps a project's updatedAt so it surfaces as recently active. Call this
 * from any mutation on a project's child records (notes today; attachments
 * once that feature exists) so "recently updated" reflects real activity
 * on the project, not just edits to its own fields.
 */
function touchProject(id: string): Project {
  const index = projects.findIndex((p) => p.id === id)
  if (index === -1) throw new Error(`Project ${id} not found`)
  const updated: Project = {
    ...projects[index],
    updatedAt: new Date().toISOString(),
  }
  projects = projects.map((p, i) => (i === index ? updated : p))
  return updated
}

export const mockApi = {
  async listProjects(): Promise<Project[]> {
    return delay(clone(projects))
  },

  async getProject(id: string): Promise<Project | null> {
    const found = projects.find((p) => p.id === id) ?? null
    return delay(found ? clone(found) : null)
  },

  async createProject(input: CreateProjectInput): Promise<Project> {
    const now = new Date().toISOString()
    const project: Project = {
      id: uid('p'),
      name: input.name.trim(),
      pitch: input.pitch?.trim() ?? '',
      description: input.description?.trim() ?? '',
      status: input.status ?? 'Inbox',
      tags: input.tags ?? [],
      excitement: input.excitement ?? 3,
      effort: input.effort ?? 3,
      potential: input.potential ?? 3,
      nextAction: input.nextAction?.trim() ?? '',
      targetDate: input.targetDate ?? null,
      links: input.links ?? [],
      createdAt: now,
      updatedAt: now,
    }
    projects = [project, ...projects]
    return delay(clone(project))
  },

  async updateProject(id: string, patch: UpdateProjectInput): Promise<Project> {
    const index = projects.findIndex((p) => p.id === id)
    if (index === -1) throw new Error(`Project ${id} not found`)
    const updated: Project = {
      ...projects[index],
      ...patch,
      updatedAt: new Date().toISOString(),
    }
    projects = projects.map((p, i) => (i === index ? updated : p))
    return delay(clone(updated))
  },

  async deleteProject(id: string): Promise<void> {
    projects = projects.filter((p) => p.id !== id)
    notes = notes.filter((n) => n.projectId !== id)
    return delay(undefined)
  },

  async listNotes(projectId: string): Promise<Note[]> {
    const result = notes
      .filter((n) => n.projectId === projectId)
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
    return delay(clone(result))
  },

  async addNote(
    projectId: string,
    body: string,
  ): Promise<{ note: Note; project: Project }> {
    const note: Note = {
      id: uid('n'),
      projectId,
      body: body.trim(),
      createdAt: new Date().toISOString(),
    }
    notes = [note, ...notes]
    const project = touchProject(projectId)
    return delay({ note: clone(note), project: clone(project) })
  },

  async deleteNote(id: string): Promise<Project> {
    const note = notes.find((n) => n.id === id)
    if (!note) throw new Error(`Note ${id} not found`)
    notes = notes.filter((n) => n.id !== id)
    return delay(clone(touchProject(note.projectId)))
  },
}

export type MockApi = typeof mockApi

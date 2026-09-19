import { seedNotes, seedProjects } from './seed'
import type {
  CreateProjectInput,
  Note,
  Project,
  UpdateProjectInput,
} from './types'

/**
 * In-memory mock backend. Projects and auth now hit the real FastAPI
 * backend (see real.ts / auth.ts); this module still backs notes and
 * attachments, which have no backend yet (see index.ts).
 *
 * Its own `projects` array only exists to support that: bumping a
 * project's updatedAt when a note is added/removed. It no longer feeds
 * the dashboard, so a real (backend-owned) project id won't be found
 * here — touchProject returns null in that case instead of throwing.
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
 *
 * Returns null if this store doesn't know the project (it belongs to the
 * real backend now) rather than throwing, so notes still work on a
 * backend-owned project; callers just skip the local touch in that case.
 */
function touchProject(id: string): Project | null {
  const index = projects.findIndex((p) => p.id === id)
  if (index === -1) return null
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
  ): Promise<{ note: Note; project: Project | null }> {
    const note: Note = {
      id: uid('n'),
      projectId,
      body: body.trim(),
      createdAt: new Date().toISOString(),
    }
    notes = [note, ...notes]
    const project = touchProject(projectId)
    return delay({
      note: clone(note),
      project: project ? clone(project) : null,
    })
  },

  async deleteNote(id: string): Promise<Project | null> {
    const note = notes.find((n) => n.id === id)
    if (!note) throw new Error(`Note ${id} not found`)
    notes = notes.filter((n) => n.id !== id)
    const project = touchProject(note.projectId)
    return delay(project ? clone(project) : null)
  },
}

export type MockApi = typeof mockApi

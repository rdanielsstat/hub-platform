// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Project } from '@/services/api'
import { StoreProvider } from '@/store'
import { useStore } from '@/use-store'
import { act, flush, renderHook } from '@/lib/render-hook'

const mockApi = vi.hoisted(() => ({
  listProjects: vi.fn(),
  getProject: vi.fn(),
  createProject: vi.fn(),
  updateProject: vi.fn(),
  deleteProject: vi.fn(),
  listNotes: vi.fn(),
  addNote: vi.fn(),
  deleteNote: vi.fn(),
}))

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/api')>()
  return { ...actual, api: mockApi }
})

vi.mock('@/lib/toast', () => ({
  notifyError: vi.fn(),
  toastManager: { add: vi.fn() },
}))

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    name: 'Test project',
    pitch: '',
    description: '',
    status: 'Active',
    tags: [],
    excitement: 3,
    effort: 3,
    potential: 3,
    nextAction: '',
    targetDate: null,
    links: [],
    createdAt: '2026-09-01T00:00:00Z',
    updatedAt: '2026-09-01T00:00:00Z',
    ...overrides,
  }
}

function setup() {
  return renderHook(() => useStore(), { wrapper: StoreProvider })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('initial load', () => {
  it('populates projects on success and clears loading', async () => {
    const projects = [project({ id: 'p1' }), project({ id: 'p2' })]
    mockApi.listProjects.mockResolvedValueOnce(projects)

    const hook = setup()
    await flush()

    expect(hook.result.projects).toEqual(projects)
    expect(hook.result.loading).toBe(false)
    expect(hook.result.error).toBeNull()
  })

  it('sets the error state on failure and leaves projects empty', async () => {
    mockApi.listProjects.mockRejectedValueOnce(new Error('network down'))

    const hook = setup()
    await flush()

    expect(hook.result.projects).toEqual([])
    expect(hook.result.loading).toBe(false)
    expect(hook.result.error).toMatch(/could not load your projects/i)
  })
})

describe('createProject', () => {
  it('adds the created project to state on success', async () => {
    mockApi.listProjects.mockResolvedValueOnce([])
    const hook = setup()
    await flush()

    const created = project({ id: 'new' })
    mockApi.createProject.mockResolvedValueOnce(created)

    let returned: Project | undefined
    await act(async () => {
      returned = await hook.result.createProject({ name: 'New' })
    })

    expect(returned).toEqual(created)
    expect(hook.result.projects).toEqual([created])
  })

  it('leaves state unchanged and rejects on failure', async () => {
    const existing = [project({ id: 'p1' })]
    mockApi.listProjects.mockResolvedValueOnce(existing)
    const hook = setup()
    await flush()

    const before = hook.result.projects
    mockApi.createProject.mockRejectedValueOnce(new Error('boom'))

    await expect(
      act(async () => {
        await hook.result.createProject({ name: 'New' })
      }),
    ).rejects.toThrow('boom')

    expect(hook.result.projects).toBe(before)
  })
})

describe('updateProject', () => {
  it('replaces the matching project on success', async () => {
    const original = project({ id: 'p1', name: 'Before' })
    mockApi.listProjects.mockResolvedValueOnce([original])
    const hook = setup()
    await flush()

    const updated = { ...original, name: 'After' }
    mockApi.updateProject.mockResolvedValueOnce(updated)

    await act(async () => {
      await hook.result.updateProject('p1', { name: 'After' })
    })

    expect(hook.result.projects).toEqual([updated])
  })

  it('leaves state unchanged and rejects on failure', async () => {
    const original = project({ id: 'p1', name: 'Before' })
    mockApi.listProjects.mockResolvedValueOnce([original])
    const hook = setup()
    await flush()

    const before = hook.result.projects
    mockApi.updateProject.mockRejectedValueOnce(new Error('boom'))

    await expect(
      act(async () => {
        await hook.result.updateProject('p1', { name: 'After' })
      }),
    ).rejects.toThrow('boom')

    expect(hook.result.projects).toBe(before)
  })
})

describe('deleteProject', () => {
  it('removes the matching project on success', async () => {
    const projects = [project({ id: 'p1' }), project({ id: 'p2' })]
    mockApi.listProjects.mockResolvedValueOnce(projects)
    const hook = setup()
    await flush()

    mockApi.deleteProject.mockResolvedValueOnce(undefined)

    await act(async () => {
      await hook.result.deleteProject('p1')
    })

    expect(hook.result.projects).toEqual([projects[1]])
  })

  it('leaves state unchanged and rejects on failure', async () => {
    const projects = [project({ id: 'p1' })]
    mockApi.listProjects.mockResolvedValueOnce(projects)
    const hook = setup()
    await flush()

    const before = hook.result.projects
    mockApi.deleteProject.mockRejectedValueOnce(new Error('boom'))

    await expect(
      act(async () => {
        await hook.result.deleteProject('p1')
      }),
    ).rejects.toThrow('boom')

    expect(hook.result.projects).toBe(before)
  })
})

describe('addNote', () => {
  it('bumps the parent project to the returned version on success', async () => {
    const original = project({ id: 'p1', name: 'Before' })
    mockApi.listProjects.mockResolvedValueOnce([original])
    const hook = setup()
    await flush()

    const note = { id: 'n1', projectId: 'p1', body: 'hi', createdAt: 'now' }
    const bumped = { ...original, updatedAt: 'later' }
    mockApi.addNote.mockResolvedValueOnce({ note, project: bumped })

    let returnedNote
    await act(async () => {
      returnedNote = await hook.result.addNote('p1', 'hi')
    })

    expect(returnedNote).toEqual(note)
    expect(hook.result.projects).toEqual([bumped])
  })

  it('leaves state unchanged and rejects on failure', async () => {
    const original = project({ id: 'p1' })
    mockApi.listProjects.mockResolvedValueOnce([original])
    const hook = setup()
    await flush()

    const before = hook.result.projects
    mockApi.addNote.mockRejectedValueOnce(new Error('boom'))

    await expect(
      act(async () => {
        await hook.result.addNote('p1', 'hi')
      }),
    ).rejects.toThrow('boom')

    expect(hook.result.projects).toBe(before)
  })
})

describe('deleteNote', () => {
  it('bumps the parent project to the returned version on success', async () => {
    const original = project({ id: 'p1' })
    mockApi.listProjects.mockResolvedValueOnce([original])
    const hook = setup()
    await flush()

    const bumped = { ...original, updatedAt: 'later' }
    mockApi.deleteNote.mockResolvedValueOnce(bumped)

    await act(async () => {
      await hook.result.deleteNote('n1')
    })

    expect(hook.result.projects).toEqual([bumped])
  })

  it('leaves state unchanged and rejects on failure', async () => {
    const original = project({ id: 'p1' })
    mockApi.listProjects.mockResolvedValueOnce([original])
    const hook = setup()
    await flush()

    const before = hook.result.projects
    mockApi.deleteNote.mockRejectedValueOnce(new Error('boom'))

    await expect(
      act(async () => {
        await hook.result.deleteNote('n1')
      }),
    ).rejects.toThrow('boom')

    expect(hook.result.projects).toBe(before)
  })
})

describe('getProject', () => {
  it('finds a project by id', async () => {
    const projects = [project({ id: 'p1' }), project({ id: 'p2' })]
    mockApi.listProjects.mockResolvedValueOnce(projects)
    const hook = setup()
    await flush()

    expect(hook.result.getProject('p2')).toEqual(projects[1])
    expect(hook.result.getProject('missing')).toBeUndefined()
  })
})

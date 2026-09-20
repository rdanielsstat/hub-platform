import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { StoreProvider } from '@/store'
import type { Project } from '@/services/api'
import { DashboardPage } from './dashboard'

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
    pitch: 'A pitch',
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

function renderDashboard(onCapture = vi.fn()) {
  return render(
    <MemoryRouter>
      <StoreProvider>
        <DashboardPage onCapture={onCapture} />
      </StoreProvider>
    </MemoryRouter>,
  )
}

function cardFor(name: string) {
  return screen.getByText(name).closest('a')!
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('DashboardPage states', () => {
  it('does not show final content while the initial load is pending', () => {
    mockApi.listProjects.mockReturnValueOnce(new Promise(() => {}))
    renderDashboard()

    expect(screen.queryByText(/nothing captured yet/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  it('shows a load error with a working retry', async () => {
    const user = userEvent.setup()
    mockApi.listProjects.mockRejectedValueOnce(new Error('network down'))
    renderDashboard()

    expect(
      await screen.findByText(/couldn't load your ideas/i),
    ).toBeInTheDocument()

    mockApi.listProjects.mockResolvedValueOnce([project({ name: 'Recovered' })])
    await user.click(screen.getByRole('button', { name: /try again/i }))

    expect(await screen.findByText('Recovered')).toBeInTheDocument()
  })

  it('shows an empty state with a quick-capture action when there are no projects', async () => {
    const onCapture = vi.fn()
    const user = userEvent.setup()
    mockApi.listProjects.mockResolvedValueOnce([])
    renderDashboard(onCapture)

    expect(await screen.findByText(/nothing captured yet/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /quick capture/i }))
    expect(onCapture).toHaveBeenCalledTimes(1)
  })

  it('shows a no-matches state with clear filters when a search matches nothing', async () => {
    const user = userEvent.setup()
    mockApi.listProjects.mockResolvedValueOnce([project({ name: 'Chess app' })])
    renderDashboard()

    await screen.findByText('Chess app')
    await user.type(
      screen.getByPlaceholderText(/search ideas/i),
      'nonexistent-query',
    )

    expect(await screen.findByText(/no matches/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /clear filters/i }))
    expect(await screen.findByText('Chess app')).toBeInTheDocument()
  })
})

describe('DashboardPage populated', () => {
  const projects = [
    project({
      id: 'p1',
      name: 'Chess analytics',
      pitch: 'Track chess games',
      status: 'Active',
      tags: ['chess', 'stats'],
      updatedAt: '2026-09-19T00:00:00Z',
    }),
    project({
      id: 'p2',
      name: 'Garden planner',
      pitch: 'Plan the garden',
      status: 'Inbox',
      tags: ['garden'],
      updatedAt: '2026-09-18T00:00:00Z',
    }),
    project({
      id: 'p3',
      name: 'Quick win idea',
      pitch: 'Should be flagged',
      status: 'Exploring',
      excitement: 5,
      effort: 1,
      tags: [],
      updatedAt: '2026-09-17T00:00:00Z',
    }),
    project({
      id: 'p4',
      name: 'Stale idea',
      pitch: 'Has not moved',
      status: 'Active',
      excitement: 2,
      effort: 4,
      tags: [],
      updatedAt: new Date(Date.now() - 90 * 86400000).toISOString(),
    }),
  ]

  beforeEach(() => {
    mockApi.listProjects.mockResolvedValue(projects.map((p) => ({ ...p })))
  })

  it('renders all projects as cards', async () => {
    renderDashboard()
    expect(await screen.findByText('Chess analytics')).toBeInTheDocument()
    expect(screen.getByText('Garden planner')).toBeInTheDocument()
    expect(screen.getByText('Quick win idea')).toBeInTheDocument()
    expect(screen.getByText('Stale idea')).toBeInTheDocument()
  })

  it('shows the quick-win badge only on the qualifying card', async () => {
    renderDashboard()
    await screen.findByText('Chess analytics')

    expect(
      within(cardFor('Quick win idea')).getByText('Quick win'),
    ).toBeInTheDocument()
    expect(
      within(cardFor('Chess analytics')).queryByText('Quick win'),
    ).not.toBeInTheDocument()
  })

  it('shows the stale badge only on the qualifying card', async () => {
    renderDashboard()
    await screen.findByText('Chess analytics')

    expect(within(cardFor('Stale idea')).getByText('Stale')).toBeInTheDocument()
    expect(
      within(cardFor('Chess analytics')).queryByText('Stale'),
    ).not.toBeInTheDocument()
  })

  it('filters by status when a stats chip is clicked', async () => {
    const user = userEvent.setup()
    renderDashboard()
    await screen.findByText('Chess analytics')

    await user.click(screen.getByRole('button', { name: /^inbox/i }))

    expect(screen.getByText('Garden planner')).toBeInTheDocument()
    expect(screen.queryByText('Chess analytics')).not.toBeInTheDocument()
    expect(screen.queryByText('Quick win idea')).not.toBeInTheDocument()
  })

  it('filters by tag when a tag chip is clicked', async () => {
    const user = userEvent.setup()
    renderDashboard()
    await screen.findByText('Chess analytics')

    await user.click(screen.getByRole('button', { name: '#garden' }))

    expect(screen.getByText('Garden planner')).toBeInTheDocument()
    expect(screen.queryByText('Chess analytics')).not.toBeInTheDocument()
  })

  it('filters by search query across name and pitch', async () => {
    const user = userEvent.setup()
    renderDashboard()
    await screen.findByText('Chess analytics')

    await user.type(screen.getByPlaceholderText(/search ideas/i), 'garden')

    expect(screen.getByText('Garden planner')).toBeInTheDocument()
    expect(screen.queryByText('Chess analytics')).not.toBeInTheDocument()
  })

  it('sorts by name A-Z', async () => {
    const user = userEvent.setup()
    renderDashboard()
    await screen.findByText('Chess analytics')

    await user.selectOptions(
      screen.getByRole('combobox', { name: /sort projects/i }),
      'Name (A–Z)',
    )

    const headings = screen.getAllByRole('heading', { level: 3 })
    expect(headings.map((h) => h.textContent)).toEqual([
      'Chess analytics',
      'Garden planner',
      'Quick win idea',
      'Stale idea',
    ])
  })

  it('sorts by lowest effort', async () => {
    const user = userEvent.setup()
    renderDashboard()
    await screen.findByText('Chess analytics')

    await user.selectOptions(
      screen.getByRole('combobox', { name: /sort projects/i }),
      'Lowest effort',
    )

    const headings = screen.getAllByRole('heading', { level: 3 })
    // p3 (effort 1) first, p4 (effort 4) last; p1/p2 (effort 3) in between.
    expect(headings[0]).toHaveTextContent('Quick win idea')
    expect(headings[headings.length - 1]).toHaveTextContent('Stale idea')
  })
})

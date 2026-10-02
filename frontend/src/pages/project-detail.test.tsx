import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { StoreProvider } from '@/store'
import type { Project } from '@/services/api'
import { ProjectDetailPage } from './project-detail'

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
    name: 'Chess analytics',
    pitch: 'Track my chess games',
    description: 'A longer brain dump about chess analytics.',
    status: 'Active',
    tags: ['chess'],
    excitement: 3,
    effort: 3,
    potential: 3,
    nextAction: 'Set up the database',
    targetDate: null,
    links: [],
    createdAt: '2026-09-01T00:00:00Z',
    updatedAt: '2026-09-01T00:00:00Z',
    ...overrides,
  }
}

function renderDetail(id = 'p1') {
  return render(
    <MemoryRouter initialEntries={[`/project/${id}`]}>
      <StoreProvider>
        <Routes>
          <Route path="/project/:id" element={<ProjectDetailPage />} />
          <Route path="/" element={<div>Dashboard</div>} />
        </Routes>
      </StoreProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockApi.listNotes.mockResolvedValue([])
})

describe('ProjectDetailPage rendering', () => {
  it("renders the project's fields", async () => {
    mockApi.listProjects.mockResolvedValueOnce([project()])
    renderDetail()

    expect(
      await screen.findByDisplayValue('Chess analytics'),
    ).toBeInTheDocument()
    expect(screen.getByDisplayValue('Track my chess games')).toBeInTheDocument()
    expect(
      screen.getByDisplayValue('A longer brain dump about chess analytics.'),
    ).toBeInTheDocument()
    expect(screen.getByDisplayValue('Set up the database')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: /status/i })).toHaveValue(
      'Active',
    )
    expect(screen.getByText('#chess')).toBeInTheDocument()
    expect(screen.getByText('No links yet.')).toBeInTheDocument()
  })

  it('shows a not-found state for an id that does not exist', async () => {
    mockApi.listProjects.mockResolvedValueOnce([project({ id: 'other' })])
    renderDetail('missing')

    expect(await screen.findByText(/idea not found/i)).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: /back to dashboard/i }),
    ).toHaveAttribute('href', '/')
  })

  it('shows a load-error state with a working retry when the fetch fails', async () => {
    const user = userEvent.setup()
    mockApi.listProjects.mockRejectedValueOnce(new Error('network down'))
    renderDetail('p1')

    expect(
      await screen.findByText(/couldn't load this idea/i),
    ).toBeInTheDocument()

    mockApi.listProjects.mockResolvedValueOnce([project()])
    await user.click(screen.getByRole('button', { name: /try again/i }))

    expect(
      await screen.findByDisplayValue('Chess analytics'),
    ).toBeInTheDocument()
  })
})

describe('ProjectDetailPage field editing', () => {
  it('saves a changed field on blur', async () => {
    const user = userEvent.setup()
    mockApi.listProjects.mockResolvedValueOnce([project()])
    mockApi.updateProject.mockResolvedValueOnce(
      project({ pitch: 'New pitch text' }),
    )
    renderDetail()

    const pitchInput = await screen.findByDisplayValue('Track my chess games')
    await user.clear(pitchInput)
    await user.type(pitchInput, 'New pitch text')
    await user.tab()

    expect(mockApi.updateProject).toHaveBeenCalledWith('p1', {
      pitch: 'New pitch text',
    })
  })

  it('does not save on blur when the field is unchanged', async () => {
    const user = userEvent.setup()
    mockApi.listProjects.mockResolvedValueOnce([project()])
    renderDetail()

    const nameInput = await screen.findByDisplayValue('Chess analytics')
    await user.click(nameInput)
    await user.tab()

    expect(mockApi.updateProject).not.toHaveBeenCalled()
  })

  it('saves the description on blur', async () => {
    const user = userEvent.setup()
    mockApi.listProjects.mockResolvedValueOnce([project()])
    mockApi.updateProject.mockResolvedValueOnce(
      project({ description: 'Updated brain dump.' }),
    )
    renderDetail()

    const description = await screen.findByDisplayValue(
      'A longer brain dump about chess analytics.',
    )
    await user.clear(description)
    await user.type(description, 'Updated brain dump.')
    await user.tab()

    expect(mockApi.updateProject).toHaveBeenCalledWith('p1', {
      description: 'Updated brain dump.',
    })
  })

  it('saves the pinned next-action field on blur', async () => {
    const user = userEvent.setup()
    mockApi.listProjects.mockResolvedValueOnce([project()])
    mockApi.updateProject.mockResolvedValueOnce(
      project({ nextAction: 'Ship the first chart' }),
    )
    renderDetail()

    const nextAction = await screen.findByDisplayValue('Set up the database')
    await user.clear(nextAction)
    await user.type(nextAction, 'Ship the first chart')
    await user.tab()

    expect(mockApi.updateProject).toHaveBeenCalledWith('p1', {
      nextAction: 'Ship the first chart',
    })
  })

  it('reverts the field locally when the save fails', async () => {
    const user = userEvent.setup()
    mockApi.listProjects.mockResolvedValueOnce([project()])
    mockApi.updateProject.mockRejectedValueOnce(new Error('boom'))
    renderDetail()

    const pitchInput = await screen.findByDisplayValue('Track my chess games')
    await user.clear(pitchInput)
    await user.type(pitchInput, 'This will fail')
    await user.tab()

    expect(
      await screen.findByDisplayValue('Track my chess games'),
    ).toBeInTheDocument()
  })

  it('changes status immediately on select, without needing a blur', async () => {
    const user = userEvent.setup()
    mockApi.listProjects.mockResolvedValueOnce([project()])
    mockApi.updateProject.mockResolvedValueOnce(project({ status: 'Parked' }))
    renderDetail()

    await screen.findByDisplayValue('Chess analytics')
    await user.selectOptions(
      screen.getByRole('combobox', { name: /status/i }),
      'Parked',
    )

    expect(mockApi.updateProject).toHaveBeenCalledWith('p1', {
      status: 'Parked',
    })
  })

  it('changes a score on click', async () => {
    const user = userEvent.setup()
    mockApi.listProjects.mockResolvedValueOnce([project({ excitement: 2 })])
    mockApi.updateProject.mockResolvedValueOnce(project({ excitement: 5 }))
    renderDetail()

    await screen.findByDisplayValue('Chess analytics')
    await user.click(screen.getByRole('button', { name: 'Excitement 5 of 5' }))

    expect(mockApi.updateProject).toHaveBeenCalledWith('p1', { excitement: 5 })
  })

  it('sets the target date and shows the formatted date', async () => {
    mockApi.listProjects.mockResolvedValueOnce([project()])
    mockApi.updateProject.mockResolvedValueOnce(
      project({ targetDate: '2026-12-25' }),
    )
    renderDetail()

    const dateInput = await screen.findByLabelText(/target date/i)
    // user-event's typing doesn't reliably drive native <input type="date">
    // in jsdom, so this one uses fireEvent directly.
    fireEvent.change(dateInput, { target: { value: '2026-12-25' } })

    expect(mockApi.updateProject).toHaveBeenCalledWith('p1', {
      targetDate: '2026-12-25',
    })
    expect(await screen.findByText('Dec 25, 2026')).toBeInTheDocument()
  })
})

describe('ProjectDetailPage tags and links', () => {
  it('adds a tag on Enter', async () => {
    const user = userEvent.setup()
    mockApi.listProjects.mockResolvedValueOnce([project()])
    mockApi.updateProject.mockResolvedValueOnce(
      project({ tags: ['chess', 'stats'] }),
    )
    renderDetail()

    await screen.findByDisplayValue('Chess analytics')
    await user.type(screen.getByPlaceholderText(/add a tag/i), 'stats{enter}')

    expect(mockApi.updateProject).toHaveBeenCalledWith('p1', {
      tags: ['chess', 'stats'],
    })
  })

  it('removes a tag', async () => {
    const user = userEvent.setup()
    mockApi.listProjects.mockResolvedValueOnce([project({ tags: ['chess'] })])
    mockApi.updateProject.mockResolvedValueOnce(project({ tags: [] }))
    renderDetail()

    await screen.findByDisplayValue('Chess analytics')
    await user.click(screen.getByRole('button', { name: 'Remove tag chess' }))

    expect(mockApi.updateProject).toHaveBeenCalledWith('p1', { tags: [] })
  })

  it('adds an unlabeled link, normalizing a bare domain to https', async () => {
    const user = userEvent.setup()
    mockApi.listProjects.mockResolvedValueOnce([project()])
    mockApi.updateProject.mockResolvedValueOnce(
      project({ links: [{ url: 'https://example.com' }] }),
    )
    renderDetail()

    await screen.findByDisplayValue('Chess analytics')
    await user.type(screen.getByPlaceholderText('https://…'), 'example.com')
    await user.click(screen.getByRole('button', { name: 'Add link' }))

    expect(mockApi.updateProject).toHaveBeenCalledWith('p1', {
      links: [{ url: 'https://example.com' }],
    })
  })

  it('adds a labeled link', async () => {
    const user = userEvent.setup()
    mockApi.listProjects.mockResolvedValueOnce([project()])
    mockApi.updateProject.mockResolvedValueOnce(
      project({ links: [{ label: 'Docs', url: 'https://example.com/docs' }] }),
    )
    renderDetail()

    await screen.findByDisplayValue('Chess analytics')
    await user.type(screen.getByPlaceholderText(/label \(optional\)/i), 'Docs')
    await user.type(
      screen.getByPlaceholderText('https://…'),
      'https://example.com/docs',
    )
    await user.click(screen.getByRole('button', { name: 'Add link' }))

    expect(mockApi.updateProject).toHaveBeenCalledWith('p1', {
      links: [{ label: 'Docs', url: 'https://example.com/docs' }],
    })
  })

  it('removes a link', async () => {
    const user = userEvent.setup()
    mockApi.listProjects.mockResolvedValueOnce([
      project({ links: [{ label: 'Docs', url: 'https://example.com' }] }),
    ])
    mockApi.updateProject.mockResolvedValueOnce(project({ links: [] }))
    renderDetail()

    await screen.findByDisplayValue('Chess analytics')
    await user.click(screen.getByRole('button', { name: 'Remove link Docs' }))

    expect(mockApi.updateProject).toHaveBeenCalledWith('p1', { links: [] })
  })

  it('renders an http(s) link as a link', async () => {
    mockApi.listProjects.mockResolvedValueOnce([
      project({ links: [{ label: 'Docs', url: 'https://example.com' }] }),
    ])
    renderDetail()

    expect(await screen.findByRole('link', { name: 'Docs' })).toHaveAttribute(
      'href',
      'https://example.com',
    )
  })

  it.each(['javascript:alert(1)', 'file:///etc/passwd', 'data:text/html,hi'])(
    'renders a stored %s link as plain text, never an href',
    async (url) => {
      mockApi.listProjects.mockResolvedValueOnce([
        project({ links: [{ label: 'Sketchy', url }] }),
      ])
      renderDetail()

      expect(await screen.findByText('Sketchy')).toBeInTheDocument()
      expect(screen.queryByRole('link', { name: 'Sketchy' })).toBeNull()
      expect(document.querySelector(`a[href="${url}"]`)).toBeNull()
      // Still removable.
      expect(
        screen.getByRole('button', { name: 'Remove link Sketchy' }),
      ).toBeInTheDocument()
    },
  )
})

describe('ProjectDetailPage delete', () => {
  it('requires a two-step confirm before deleting, then navigates home', async () => {
    const user = userEvent.setup()
    mockApi.listProjects.mockResolvedValueOnce([project()])
    mockApi.deleteProject.mockResolvedValueOnce(undefined)
    renderDetail()

    await screen.findByDisplayValue('Chess analytics')
    await user.click(screen.getByRole('button', { name: /delete idea/i }))

    expect(screen.getByText(/delete this idea\?/i)).toBeInTheDocument()
    expect(mockApi.deleteProject).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: /^delete$/i }))

    expect(mockApi.deleteProject).toHaveBeenCalledWith('p1')
    expect(await screen.findByText('Dashboard')).toBeInTheDocument()
  })

  it('cancel backs out of the confirm without deleting', async () => {
    const user = userEvent.setup()
    mockApi.listProjects.mockResolvedValueOnce([project()])
    renderDetail()

    await screen.findByDisplayValue('Chess analytics')
    await user.click(screen.getByRole('button', { name: /delete idea/i }))
    await user.click(screen.getByRole('button', { name: /cancel/i }))

    expect(mockApi.deleteProject).not.toHaveBeenCalled()
    expect(
      screen.getByRole('button', { name: /delete idea/i }),
    ).toBeInTheDocument()
  })
})

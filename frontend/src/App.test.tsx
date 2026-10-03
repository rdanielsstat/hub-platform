import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider } from '@/auth'
import { HttpError, type Project } from '@/services/api'
import { SESSION_RETRY_DELAY_MS } from '@/auth'
import { App } from './App'

const mockAuthApi = vi.hoisted(() => ({
  register: vi.fn(),
  login: vi.fn(),
  // No session (a 401) unless a test says otherwise; set in beforeEach,
  // since HttpError can't be imported into this hoisted block.
  getCurrentUser: vi.fn(),
  logout: vi.fn().mockResolvedValue(undefined),
}))

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
  return { ...actual, authApi: mockAuthApi, api: mockApi }
})

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    name: 'Chess analytics',
    pitch: 'Track my chess games',
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

function renderApp() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  mockApi.listNotes.mockResolvedValue([])
  mockAuthApi.getCurrentUser.mockRejectedValue(
    new HttpError(401, 'Not authenticated'),
  )
})

describe('Backend unreachable on load', () => {
  it('shows a retry screen instead of the login page, and recovers', async () => {
    const user = userEvent.setup()
    mockAuthApi.getCurrentUser
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce({
        id: 'u1',
        email: 'me@example.com',
        displayName: 'Rob',
        createdAt: 'now',
        updatedAt: 'now',
      })
    mockApi.listProjects.mockResolvedValueOnce([project()])

    renderApp()

    expect(
      await screen.findByRole(
        'heading',
        { name: 'Can’t reach the server' },
        { timeout: SESSION_RETRY_DELAY_MS + 1000 },
      ),
    ).toBeInTheDocument()
    expect(screen.queryByText('Welcome back.')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await screen.findByText('Chess analytics')).toBeInTheDocument()
  })
})

describe('Auth to dashboard flow', () => {
  it('shows login when unauthenticated, then the dashboard with their projects after logging in', async () => {
    const user = userEvent.setup()
    mockApi.listProjects.mockResolvedValueOnce([
      project({ name: 'Chess analytics' }),
    ])
    mockAuthApi.login.mockResolvedValueOnce({
      id: 'u1',
      email: 'me@example.com',
      displayName: 'Rob',
      createdAt: 'now',
      updatedAt: 'now',
    })

    renderApp()

    expect(await screen.findByText('Welcome back.')).toBeInTheDocument()

    await user.type(screen.getByLabelText(/email/i), 'me@example.com')
    await user.type(screen.getByLabelText(/password/i), 'correct-password')
    await user.click(screen.getByRole('button', { name: /log in/i }))

    expect(await screen.findByText('Chess analytics')).toBeInTheDocument()
    expect(screen.getByText('Ideas')).toBeInTheDocument()
  })
})

describe('Capture, see it, edit it flow', () => {
  it('captures a project from the dashboard, opens it, and persists an edit', async () => {
    const user = userEvent.setup()
    mockAuthApi.getCurrentUser.mockResolvedValueOnce({
      id: 'u1',
      email: 'me@example.com',
      displayName: 'Rob',
      createdAt: 'now',
      updatedAt: 'now',
    })
    mockApi.listProjects.mockResolvedValueOnce([])

    const created = project({ id: 'new-1', name: 'Garden tracker', pitch: '' })
    mockApi.createProject.mockResolvedValueOnce(created)
    mockApi.updateProject.mockResolvedValueOnce({
      ...created,
      pitch: 'Track my garden beds',
    })

    renderApp()

    // Dashboard starts empty.
    expect(await screen.findByText(/nothing captured yet/i)).toBeInTheDocument()

    // Capture a new idea from the header. The (still-closed) quick-capture
    // dialog is present but hidden in the DOM, so scope to the header
    // landmark to avoid matching its own "Capture" button too.
    const header = screen.getByRole('banner')
    await user.click(within(header).getByRole('button', { name: /capture/i }))
    const nameField = await screen.findByLabelText(/^name$/i)
    await user.type(nameField, 'Garden tracker')
    await user.click(screen.getByRole('button', { name: /^capture$/i }))

    // It shows up on the dashboard.
    expect(await screen.findByText('Garden tracker')).toBeInTheDocument()

    // Open it and edit the pitch.
    await user.click(screen.getByText('Garden tracker'))
    const pitchInput = await screen.findByPlaceholderText(
      /one-line pitch: the scannable version/i,
    )
    await user.type(pitchInput, 'Track my garden beds')
    await user.tab()

    expect(mockApi.updateProject).toHaveBeenCalledWith('new-1', {
      pitch: 'Track my garden beds',
    })
    expect(
      await screen.findByDisplayValue('Track my garden beds'),
    ).toBeInTheDocument()
  })
})

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StoreProvider } from '@/store'
import type { Note } from '@/services/api'
import { NotesPanel } from './notes-panel'
import { NOTE_MAX_LENGTH } from '@/lib/limits'

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

function note(overrides: Partial<Note> = {}): Note {
  return {
    id: 'n1',
    projectId: 'p1',
    body: 'A note',
    createdAt: '2026-09-01T00:00:00Z',
    ...overrides,
  }
}

function renderPanel() {
  return render(
    <StoreProvider>
      <NotesPanel projectId="p1" />
    </StoreProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockApi.listProjects.mockResolvedValue([])
})

describe('NotesPanel', () => {
  it('lists the fetched notes', async () => {
    mockApi.listNotes.mockResolvedValueOnce([
      note({ id: 'n1', body: 'First note' }),
      note({ id: 'n2', body: 'Second note' }),
    ])
    renderPanel()

    expect(await screen.findByText('First note')).toBeInTheDocument()
    expect(screen.getByText('Second note')).toBeInTheDocument()
  })

  it('shows an empty message when there are no notes', async () => {
    mockApi.listNotes.mockResolvedValueOnce([])
    renderPanel()

    expect(await screen.findByText(/no notes yet/i)).toBeInTheDocument()
  })

  it('caps a note at the API limit', async () => {
    const user = userEvent.setup()
    mockApi.listNotes.mockResolvedValueOnce([])
    renderPanel()
    const box = (await screen.findByPlaceholderText(
      /add a note/i,
    )) as HTMLTextAreaElement

    expect(box).toHaveAttribute('maxLength', String(NOTE_MAX_LENGTH))
    await user.click(box)
    await user.paste('b'.repeat(NOTE_MAX_LENGTH + 10))
    expect(box.value).toHaveLength(NOTE_MAX_LENGTH)
  })

  it('adds a note via the button and clears the draft', async () => {
    const user = userEvent.setup()
    mockApi.listNotes.mockResolvedValueOnce([])
    mockApi.addNote.mockResolvedValueOnce({
      note: note({ id: 'n2', body: 'A brand new note' }),
      project: {
        id: 'p1',
        name: 'x',
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
        createdAt: 'now',
        updatedAt: 'now',
      },
    })
    renderPanel()
    await screen.findByText(/no notes yet/i)

    const textarea = screen.getByPlaceholderText(/add a note/i)
    await user.type(textarea, 'A brand new note')
    await user.click(screen.getByRole('button', { name: /add note/i }))

    expect(await screen.findByText('A brand new note')).toBeInTheDocument()
    expect(textarea).toHaveValue('')
  })

  it('adds a note via cmd/ctrl+enter', async () => {
    const user = userEvent.setup()
    mockApi.listNotes.mockResolvedValueOnce([])
    mockApi.addNote.mockResolvedValueOnce({
      note: note({ id: 'n2', body: 'Shortcut note' }),
      project: {
        id: 'p1',
        name: 'x',
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
        createdAt: 'now',
        updatedAt: 'now',
      },
    })
    renderPanel()
    await screen.findByText(/no notes yet/i)

    const textarea = screen.getByPlaceholderText(/add a note/i)
    await user.type(textarea, 'Shortcut note')
    await user.keyboard('{Control>}{Enter}{/Control}')

    expect(await screen.findByText('Shortcut note')).toBeInTheDocument()
  })

  it('keeps the draft text when adding a note fails', async () => {
    const user = userEvent.setup()
    mockApi.listNotes.mockResolvedValueOnce([])
    mockApi.addNote.mockRejectedValueOnce(new Error('boom'))
    renderPanel()
    await screen.findByText(/no notes yet/i)

    const textarea = screen.getByPlaceholderText(/add a note/i)
    await user.type(textarea, 'This will fail')
    await user.click(screen.getByRole('button', { name: /add note/i }))

    expect(await screen.findByText(/no notes yet/i)).toBeInTheDocument()
    expect(textarea).toHaveValue('This will fail')
  })

  it('deletes a note after confirming', async () => {
    const user = userEvent.setup()
    mockApi.listNotes.mockResolvedValueOnce([
      note({ id: 'n1', body: 'Delete me' }),
    ])
    mockApi.deleteNote.mockResolvedValueOnce({
      id: 'p1',
      name: 'x',
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
      createdAt: 'now',
      updatedAt: 'now',
    })
    renderPanel()

    await screen.findByText('Delete me')
    await user.click(screen.getByRole('button', { name: /delete note/i }))
    expect(screen.getByText(/delete this note\?/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /^delete$/i }))

    expect(mockApi.deleteNote).toHaveBeenCalledWith('n1')
    expect(await screen.findByText(/no notes yet/i)).toBeInTheDocument()
  })

  it('cancel backs out without deleting', async () => {
    const user = userEvent.setup()
    mockApi.listNotes.mockResolvedValueOnce([
      note({ id: 'n1', body: 'Keep me' }),
    ])
    renderPanel()

    await screen.findByText('Keep me')
    await user.click(screen.getByRole('button', { name: /delete note/i }))
    await user.click(screen.getByRole('button', { name: /cancel/i }))

    expect(mockApi.deleteNote).not.toHaveBeenCalled()
    expect(screen.getByText('Keep me')).toBeInTheDocument()
  })

  it('leaves the note in place when deleting fails (pessimistic)', async () => {
    const user = userEvent.setup()
    mockApi.listNotes.mockResolvedValueOnce([
      note({ id: 'n1', body: 'Stubborn note' }),
    ])
    mockApi.deleteNote.mockRejectedValueOnce(new Error('boom'))
    renderPanel()

    await screen.findByText('Stubborn note')
    await user.click(screen.getByRole('button', { name: /delete note/i }))
    await user.click(screen.getByRole('button', { name: /^delete$/i }))

    expect(await screen.findByText('Stubborn note')).toBeInTheDocument()
  })
})

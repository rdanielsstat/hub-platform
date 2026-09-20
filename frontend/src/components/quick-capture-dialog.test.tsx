import { useState } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { StoreProvider } from '@/store'
import { QuickCaptureDialog } from './quick-capture-dialog'

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

/** Mirrors how AuthenticatedApp actually controls the dialog: local open state, toggled by a button. */
function Harness() {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button onClick={() => setOpen(true)}>Open capture</button>
      <QuickCaptureDialog open={open} onClose={() => setOpen(false)} />
    </>
  )
}

function renderDialog() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <StoreProvider>
        <Routes>
          <Route path="/" element={<Harness />} />
          <Route path="/project/:id" element={<div>Project page</div>} />
        </Routes>
      </StoreProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockApi.listProjects.mockResolvedValue([])
})

describe('QuickCaptureDialog', () => {
  it('is closed until opened', async () => {
    renderDialog()
    expect(
      screen.queryByText('Get it out of your head. Only a name is required.'),
    ).not.toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /open capture/i }))
    expect(
      await screen.findByText(
        'Get it out of your head. Only a name is required.',
      ),
    ).toBeInTheDocument()
  })

  it('focuses the name field on open', async () => {
    const user = userEvent.setup()
    renderDialog()
    await user.click(screen.getByRole('button', { name: /open capture/i }))

    const name = await screen.findByLabelText(/^name$/i)
    expect(name).toHaveFocus()
  })

  it('disables both capture buttons until a name is entered', async () => {
    const user = userEvent.setup()
    renderDialog()
    await user.click(screen.getByRole('button', { name: /open capture/i }))

    const capture = await screen.findByRole('button', { name: /^capture$/i })
    const captureOpen = screen.getByRole('button', { name: /capture & open/i })
    expect(capture).toBeDisabled()
    expect(captureOpen).toBeDisabled()

    await user.type(await screen.findByLabelText(/^name$/i), 'New idea')
    expect(capture).toBeEnabled()
    expect(captureOpen).toBeEnabled()
  })

  it('creates a project on submit and closes the dialog', async () => {
    const user = userEvent.setup()
    mockApi.createProject.mockResolvedValueOnce({
      id: 'new-1',
      name: 'New idea',
      pitch: '',
      description: '',
      status: 'Inbox',
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
    renderDialog()
    await user.click(screen.getByRole('button', { name: /open capture/i }))

    await user.type(await screen.findByLabelText(/^name$/i), 'New idea')
    await user.click(screen.getByRole('button', { name: /^capture$/i }))

    expect(mockApi.createProject).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'New idea', tags: [] }),
    )
    expect(
      screen.queryByText('Get it out of your head. Only a name is required.'),
    ).not.toBeInTheDocument()
  })

  it('splits comma-separated tags and drops blanks', async () => {
    const user = userEvent.setup()
    mockApi.createProject.mockResolvedValueOnce({
      id: 'new-1',
      name: 'New idea',
      pitch: '',
      description: '',
      status: 'Inbox',
      tags: ['chess', 'stats'],
      excitement: 3,
      effort: 3,
      potential: 3,
      nextAction: '',
      targetDate: null,
      links: [],
      createdAt: 'now',
      updatedAt: 'now',
    })
    renderDialog()
    await user.click(screen.getByRole('button', { name: /open capture/i }))
    await user.type(await screen.findByLabelText(/^name$/i), 'New idea')
    await user.click(screen.getByRole('button', { name: /more details/i }))
    await user.type(screen.getByLabelText(/^tags$/i), 'chess, , stats,')
    await user.click(screen.getByRole('button', { name: /^capture$/i }))

    expect(mockApi.createProject).toHaveBeenCalledWith(
      expect.objectContaining({ tags: ['chess', 'stats'] }),
    )
  })

  it('navigates to the new project on "Capture & open"', async () => {
    const user = userEvent.setup()
    mockApi.createProject.mockResolvedValueOnce({
      id: 'new-1',
      name: 'New idea',
      pitch: '',
      description: '',
      status: 'Inbox',
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
    renderDialog()
    await user.click(screen.getByRole('button', { name: /open capture/i }))
    await user.type(await screen.findByLabelText(/^name$/i), 'New idea')
    await user.click(screen.getByRole('button', { name: /capture & open/i }))

    expect(await screen.findByText('Project page')).toBeInTheDocument()
  })

  it('submits on Enter in the name field', async () => {
    const user = userEvent.setup()
    mockApi.createProject.mockResolvedValueOnce({
      id: 'new-1',
      name: 'New idea',
      pitch: '',
      description: '',
      status: 'Inbox',
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
    renderDialog()
    await user.click(screen.getByRole('button', { name: /open capture/i }))
    await user.type(await screen.findByLabelText(/^name$/i), 'New idea{enter}')

    expect(mockApi.createProject).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'New idea' }),
    )
  })

  it('stays open with the typed data intact when the create fails', async () => {
    const user = userEvent.setup()
    mockApi.createProject.mockRejectedValueOnce(new Error('boom'))
    renderDialog()
    await user.click(screen.getByRole('button', { name: /open capture/i }))
    await user.type(await screen.findByLabelText(/^name$/i), 'New idea')
    await user.type(screen.getByLabelText(/one-line pitch/i), 'My pitch')
    await user.click(screen.getByRole('button', { name: /^capture$/i }))

    expect(
      await screen.findByText(
        'Get it out of your head. Only a name is required.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByDisplayValue('New idea')).toBeInTheDocument()
    expect(screen.getByDisplayValue('My pitch')).toBeInTheDocument()
    expect(screen.queryByText('Project page')).not.toBeInTheDocument()
  })

  it('cancel closes the dialog and resets it for next time', async () => {
    const user = userEvent.setup()
    renderDialog()
    await user.click(screen.getByRole('button', { name: /open capture/i }))
    await user.type(await screen.findByLabelText(/^name$/i), 'Throwaway')
    await user.click(screen.getByRole('button', { name: /cancel/i }))

    expect(
      screen.queryByText('Get it out of your head. Only a name is required.'),
    ).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /open capture/i }))
    expect(await screen.findByLabelText(/^name$/i)).toHaveValue('')
  })
})

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider } from '@/auth'
import { AppHeader } from './app-header'

const mockAuthApi = vi.hoisted(() => ({
  register: vi.fn(),
  login: vi.fn(),
  // No session unless a test says otherwise.
  getCurrentUser: vi.fn().mockRejectedValue(new Error('Not authenticated')),
  logout: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/api')>()
  return { ...actual, authApi: mockAuthApi }
})

function renderHeader(onCapture = vi.fn()) {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <AppHeader onCapture={onCapture} />
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  document.documentElement.classList.remove('dark')
})

describe('AppHeader', () => {
  it("shows the signed-in user's display name once loaded", async () => {
    mockAuthApi.getCurrentUser.mockResolvedValueOnce({
      id: 'u1',
      email: 'me@example.com',
      displayName: 'Rob',
      createdAt: 'now',
      updatedAt: 'now',
    })
    renderHeader()
    expect(await screen.findByText('Rob')).toBeInTheDocument()
  })

  it('falls back to email when there is no display name', async () => {
    mockAuthApi.getCurrentUser.mockResolvedValueOnce({
      id: 'u1',
      email: 'me@example.com',
      displayName: null,
      createdAt: 'now',
      updatedAt: 'now',
    })
    renderHeader()
    expect(await screen.findByText('me@example.com')).toBeInTheDocument()
  })

  it('calls onCapture when quick capture is clicked', async () => {
    const user = userEvent.setup()
    const onCapture = vi.fn()
    mockAuthApi.getCurrentUser.mockResolvedValueOnce({
      id: 'u1',
      email: 'me@example.com',
      displayName: null,
      createdAt: 'now',
      updatedAt: 'now',
    })
    renderHeader(onCapture)
    await screen.findByText('me@example.com')

    await user.click(
      screen.getByRole('button', { name: /quick capture|^capture$/i }),
    )
    expect(onCapture).toHaveBeenCalledTimes(1)
  })

  it('toggles dark mode and updates the button label', async () => {
    const user = userEvent.setup()
    mockAuthApi.getCurrentUser.mockResolvedValueOnce({
      id: 'u1',
      email: 'me@example.com',
      displayName: null,
      createdAt: 'now',
      updatedAt: 'now',
    })
    renderHeader()
    await screen.findByText('me@example.com')

    const toggle = screen.getByRole('button', { name: /switch to dark mode/i })
    await user.click(toggle)

    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(
      screen.getByRole('button', { name: /switch to light mode/i }),
    ).toBeInTheDocument()
  })

  it('signs out when the sign-out button is clicked', async () => {
    const user = userEvent.setup()
    mockAuthApi.getCurrentUser.mockResolvedValueOnce({
      id: 'u1',
      email: 'me@example.com',
      displayName: null,
      createdAt: 'now',
      updatedAt: 'now',
    })
    renderHeader()
    await screen.findByText('me@example.com')

    await user.click(screen.getByRole('button', { name: /sign out/i }))
    expect(mockAuthApi.logout).toHaveBeenCalledTimes(1)
  })
})

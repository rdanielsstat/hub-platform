import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from '@/auth'
import { HttpError } from '@/services/api'
import { LoginPage } from './login'
import { EMAIL_MAX_LENGTH, PASSWORD_MAX_LENGTH } from '@/lib/limits'

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

function renderLoginPage() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<div>Home</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
})

describe('LoginPage', () => {
  it('renders the login form', () => {
    renderLoginPage()
    expect(screen.getByText('Welcome back.')).toBeInTheDocument()
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /log in/i })).toBeInTheDocument()
  })

  it('caps email and password at the API limits', () => {
    renderLoginPage()
    expect(screen.getByLabelText(/email/i)).toHaveAttribute(
      'maxLength',
      String(EMAIL_MAX_LENGTH),
    )
    expect(screen.getByLabelText(/password/i)).toHaveAttribute(
      'maxLength',
      String(PASSWORD_MAX_LENGTH),
    )
  })

  it('disables submit until both fields are filled', async () => {
    const user = userEvent.setup()
    renderLoginPage()
    const submit = screen.getByRole('button', { name: /log in/i })
    expect(submit).toBeDisabled()

    await user.type(screen.getByLabelText(/email/i), 'me@example.com')
    expect(submit).toBeDisabled()

    await user.type(screen.getByLabelText(/password/i), 'secret123')
    expect(submit).toBeEnabled()
  })

  it('logs in with valid credentials and navigates to the dashboard', async () => {
    const user = userEvent.setup()
    mockAuthApi.login.mockResolvedValueOnce({
      id: 'u1',
      email: 'me@example.com',
      displayName: null,
      createdAt: 'now',
      updatedAt: 'now',
    })
    renderLoginPage()

    await user.type(screen.getByLabelText(/email/i), 'me@example.com')
    await user.type(screen.getByLabelText(/password/i), 'correct-password')
    await user.click(screen.getByRole('button', { name: /log in/i }))

    expect(await screen.findByText('Home')).toBeInTheDocument()
    expect(mockAuthApi.login).toHaveBeenCalledWith(
      'me@example.com',
      'correct-password',
    )
  })

  it('shows a clear error for wrong credentials and stays on the page', async () => {
    const user = userEvent.setup()
    mockAuthApi.login.mockRejectedValueOnce(
      new HttpError(401, 'Incorrect email or password'),
    )
    renderLoginPage()

    await user.type(screen.getByLabelText(/email/i), 'me@example.com')
    await user.type(screen.getByLabelText(/password/i), 'wrong-password')
    await user.click(screen.getByRole('button', { name: /log in/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Incorrect email or password',
    )
    expect(screen.queryByText('Home')).not.toBeInTheDocument()
  })

  it('shows the submit button as disabled while the request is in flight', async () => {
    const user = userEvent.setup()
    let resolveLogin!: (user: unknown) => void
    mockAuthApi.login.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveLogin = resolve
      }),
    )
    renderLoginPage()

    await user.type(screen.getByLabelText(/email/i), 'me@example.com')
    await user.type(screen.getByLabelText(/password/i), 'correct-password')
    await user.click(screen.getByRole('button', { name: /log in/i }))

    expect(screen.getByRole('button', { name: /log in/i })).toBeDisabled()

    resolveLogin({
      id: 'u1',
      email: 'me@example.com',
      displayName: null,
      createdAt: 'now',
      updatedAt: 'now',
    })
    expect(await screen.findByText('Home')).toBeInTheDocument()
  })

  it('links to the signup page', () => {
    renderLoginPage()
    expect(screen.getByRole('link', { name: /sign up/i })).toHaveAttribute(
      'href',
      '/signup',
    )
  })
})

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from '@/auth'
import { HttpError } from '@/services/api'
import { SignupPage } from './signup'
import {
  DISPLAY_NAME_MAX_LENGTH,
  EMAIL_MAX_LENGTH,
  PASSWORD_MAX_LENGTH,
} from '@/lib/limits'

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

function renderSignupPage() {
  return render(
    <MemoryRouter initialEntries={['/signup']}>
      <AuthProvider>
        <Routes>
          <Route path="/signup" element={<SignupPage />} />
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

describe('SignupPage', () => {
  it('renders the signup form', () => {
    renderSignupPage()
    expect(
      screen.getByText('Your own space to capture and triage ideas.'),
    ).toBeInTheDocument()
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/display name/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/^password/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sign up/i })).toBeInTheDocument()
  })

  it('caps each field at the API limit', async () => {
    const user = userEvent.setup()
    renderSignupPage()
    const fields: [RegExp, number][] = [
      [/email/i, EMAIL_MAX_LENGTH],
      [/display name/i, DISPLAY_NAME_MAX_LENGTH],
      [/^password/i, PASSWORD_MAX_LENGTH],
    ]
    for (const [label, limit] of fields) {
      const input = screen.getByLabelText(label) as HTMLInputElement
      expect(input).toHaveAttribute('maxLength', String(limit))
      await user.click(input)
      await user.paste('x'.repeat(limit + 10))
      expect(input.value).toHaveLength(limit)
    }
  })

  it('requires email and an 8+ character password before enabling submit', async () => {
    const user = userEvent.setup()
    renderSignupPage()
    const submit = screen.getByRole('button', { name: /sign up/i })
    expect(submit).toBeDisabled()

    await user.type(screen.getByLabelText(/email/i), 'me@example.com')
    expect(submit).toBeDisabled()

    await user.type(screen.getByLabelText(/^password/i), 'short')
    expect(submit).toBeDisabled()

    await user.type(screen.getByLabelText(/^password/i), '123')
    expect(submit).toBeEnabled()
  })

  it('registers successfully and navigates to the dashboard', async () => {
    const user = userEvent.setup()
    mockAuthApi.register.mockResolvedValueOnce({
      id: 'u1',
      email: 'new@example.com',
      displayName: null,
      createdAt: 'now',
      updatedAt: 'now',
    })
    renderSignupPage()

    await user.type(screen.getByLabelText(/email/i), 'new@example.com')
    await user.type(screen.getByLabelText(/^password/i), 'password123')
    await user.click(screen.getByRole('button', { name: /sign up/i }))

    expect(await screen.findByText('Home')).toBeInTheDocument()
    expect(mockAuthApi.register).toHaveBeenCalledWith({
      email: 'new@example.com',
      password: 'password123',
      displayName: undefined,
    })
  })

  it('shows a specific error when the email is already taken', async () => {
    const user = userEvent.setup()
    mockAuthApi.register.mockRejectedValueOnce(
      new HttpError(400, 'Email already registered'),
    )
    renderSignupPage()

    await user.type(screen.getByLabelText(/email/i), 'dupe@example.com')
    await user.type(screen.getByLabelText(/^password/i), 'password123')
    await user.click(screen.getByRole('button', { name: /sign up/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Email already registered',
    )
    expect(screen.queryByText('Home')).not.toBeInTheDocument()
  })

  it('shows the submit button as disabled while the request is in flight', async () => {
    const user = userEvent.setup()
    let resolveRegister!: (user: unknown) => void
    mockAuthApi.register.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveRegister = resolve
      }),
    )
    renderSignupPage()

    await user.type(screen.getByLabelText(/email/i), 'new@example.com')
    await user.type(screen.getByLabelText(/^password/i), 'password123')
    await user.click(screen.getByRole('button', { name: /sign up/i }))

    expect(screen.getByRole('button', { name: /sign up/i })).toBeDisabled()

    resolveRegister({
      id: 'u1',
      email: 'new@example.com',
      displayName: null,
      createdAt: 'now',
      updatedAt: 'now',
    })
    expect(await screen.findByText('Home')).toBeInTheDocument()
  })

  it('links to the login page', () => {
    renderSignupPage()
    expect(screen.getByRole('link', { name: /log in/i })).toHaveAttribute(
      'href',
      '/login',
    )
  })
})

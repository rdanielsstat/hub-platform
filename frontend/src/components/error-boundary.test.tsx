import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

const reportClientError = vi.fn()
vi.mock('@/services/api/client-errors', () => ({ reportClientError }))

const { ErrorBoundary } = await import('./error-boundary')

function ThrowingChild(): never {
  throw new Error('boom')
}

function SafeChild() {
  return <p>All good</p>
}

describe('ErrorBoundary', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    reportClientError.mockClear()
  })

  it('reports a render crash to the backend', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})

    render(
      <ErrorBoundary>
        <ThrowingChild />
      </ErrorBoundary>,
    )

    expect(reportClientError).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'render', message: 'Error: boom' }),
    )
  })

  it('reports nothing when nothing throws', () => {
    render(
      <ErrorBoundary>
        <SafeChild />
      </ErrorBoundary>,
    )

    expect(reportClientError).not.toHaveBeenCalled()
  })

  it('renders children normally when nothing throws', () => {
    render(
      <ErrorBoundary>
        <SafeChild />
      </ErrorBoundary>,
    )
    expect(screen.getByText('All good')).toBeInTheDocument()
  })

  it('renders a fallback instead of crashing when a child throws', () => {
    // React logs the caught error to the console; keep test output clean.
    vi.spyOn(console, 'error').mockImplementation(() => {})

    render(
      <ErrorBoundary>
        <ThrowingChild />
      </ErrorBoundary>,
    )

    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument()
    expect(screen.queryByText('All good')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reload/i })).toBeInTheDocument()
  })
})

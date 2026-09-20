import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DashboardToolbar } from './dashboard-toolbar'

describe('DashboardToolbar', () => {
  it('calls onQuery as the user types in search', async () => {
    const user = userEvent.setup()
    const onQuery = vi.fn()
    render(
      <DashboardToolbar
        query=""
        onQuery={onQuery}
        sort="updated"
        onSort={vi.fn()}
        tags={[]}
        activeTag={null}
        onTag={vi.fn()}
      />,
    )
    // The input is controlled by the (unchanged) `query` prop, so React
    // resets its DOM value after every keystroke; each onChange call
    // therefore reports just the single newly typed character.
    await user.type(screen.getByPlaceholderText(/search ideas/i), 'chess')
    expect(onQuery).toHaveBeenCalledTimes(5)
    expect(onQuery).toHaveBeenLastCalledWith('s')
  })

  it('shows a clear button only when there is a query, and clears it', async () => {
    const user = userEvent.setup()
    const onQuery = vi.fn()
    const { rerender } = render(
      <DashboardToolbar
        query=""
        onQuery={onQuery}
        sort="updated"
        onSort={vi.fn()}
        tags={[]}
        activeTag={null}
        onTag={vi.fn()}
      />,
    )
    expect(
      screen.queryByRole('button', { name: /clear search/i }),
    ).not.toBeInTheDocument()

    rerender(
      <DashboardToolbar
        query="chess"
        onQuery={onQuery}
        sort="updated"
        onSort={vi.fn()}
        tags={[]}
        activeTag={null}
        onTag={vi.fn()}
      />,
    )
    await user.click(screen.getByRole('button', { name: /clear search/i }))
    expect(onQuery).toHaveBeenCalledWith('')
  })

  it('calls onSort when a different sort option is chosen', async () => {
    const user = userEvent.setup()
    const onSort = vi.fn()
    render(
      <DashboardToolbar
        query=""
        onQuery={vi.fn()}
        sort="updated"
        onSort={onSort}
        tags={[]}
        activeTag={null}
        onTag={vi.fn()}
      />,
    )
    await user.selectOptions(
      screen.getByRole('combobox', { name: /sort projects/i }),
      'Opportunity score',
    )
    expect(onSort).toHaveBeenCalledWith('opportunity')
  })

  it('renders tag chips and toggles the active tag on click', async () => {
    const user = userEvent.setup()
    const onTag = vi.fn()
    render(
      <DashboardToolbar
        query=""
        onQuery={vi.fn()}
        sort="updated"
        onSort={vi.fn()}
        tags={['chess', 'stats']}
        activeTag="chess"
        onTag={onTag}
      />,
    )
    // Already-active tag toggles off
    await user.click(screen.getByRole('button', { name: '#chess' }))
    expect(onTag).toHaveBeenLastCalledWith(null)

    // Inactive tag toggles on
    await user.click(screen.getByRole('button', { name: '#stats' }))
    expect(onTag).toHaveBeenLastCalledWith('stats')
  })

  it('renders no tag chips when there are no tags', () => {
    render(
      <DashboardToolbar
        query=""
        onQuery={vi.fn()}
        sort="updated"
        onSort={vi.fn()}
        tags={[]}
        activeTag={null}
        onTag={vi.fn()}
      />,
    )
    expect(screen.queryByText(/^#/)).not.toBeInTheDocument()
  })
})

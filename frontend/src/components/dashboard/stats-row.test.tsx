import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { Project } from '@/services/api'
import { StatsRow } from './stats-row'

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    name: 'Test project',
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
    createdAt: '2026-09-01T00:00:00Z',
    updatedAt: '2026-09-01T00:00:00Z',
    ...overrides,
  }
}

describe('StatsRow', () => {
  it('shows the total count next to All and per-status counts', () => {
    const projects = [
      project({ id: 'p1', status: 'Active' }),
      project({ id: 'p2', status: 'Active' }),
      project({ id: 'p3', status: 'Inbox' }),
    ]
    render(
      <StatsRow projects={projects} activeStatus="all" onSelect={vi.fn()} />,
    )

    const all = screen.getByRole('button', { name: /all/i })
    expect(all).toHaveTextContent('3')

    const active = screen.getByRole('button', { name: /active/i })
    expect(active).toHaveTextContent('2')

    const inbox = screen.getByRole('button', { name: /inbox/i })
    expect(inbox).toHaveTextContent('1')

    const parked = screen.getByRole('button', { name: /parked/i })
    expect(parked).toHaveTextContent('0')
  })

  it('calls onSelect with the clicked status', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    render(
      <StatsRow
        projects={[project({ status: 'Active' })]}
        activeStatus="all"
        onSelect={onSelect}
      />,
    )

    await user.click(screen.getByRole('button', { name: /active/i }))
    expect(onSelect).toHaveBeenCalledWith('Active')

    await user.click(screen.getByRole('button', { name: /^all/i }))
    expect(onSelect).toHaveBeenCalledWith('all')
  })
})

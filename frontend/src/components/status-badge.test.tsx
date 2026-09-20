import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { STATUSES } from '@/services/api'
import { StatusBadge } from './status-badge'

describe('StatusBadge', () => {
  it.each(STATUSES)('renders the %s label', (status) => {
    render(<StatusBadge status={status} />)
    expect(screen.getByText(status)).toBeInTheDocument()
  })
})

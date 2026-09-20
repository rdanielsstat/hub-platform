import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { IndicatorBadge } from './indicator-badge'

describe('IndicatorBadge', () => {
  it('renders the given label', () => {
    render(<IndicatorBadge label="Quick win" className="" dotClassName="" />)
    expect(screen.getByText('Quick win')).toBeInTheDocument()
  })
})

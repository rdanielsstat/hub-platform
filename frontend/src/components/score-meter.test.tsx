import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ScorePicker } from './score-meter'

describe('ScorePicker', () => {
  it('renders the label and the current value out of 5', () => {
    render(
      <ScorePicker
        label="Excitement"
        value={3}
        onChange={vi.fn()}
        tone="excitement"
      />,
    )
    expect(screen.getByText('Excitement')).toBeInTheDocument()
    expect(screen.getByText('3/5')).toBeInTheDocument()
  })

  it('marks buttons at or below the current value as pressed', () => {
    render(
      <ScorePicker
        label="Excitement"
        value={3}
        onChange={vi.fn()}
        tone="excitement"
      />,
    )
    for (let n = 1; n <= 5; n++) {
      const button = screen.getByRole('button', {
        name: `Excitement ${n} of 5`,
      })
      expect(button).toHaveAttribute('aria-pressed', n <= 3 ? 'true' : 'false')
    }
  })

  it('calls onChange with the clicked value', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <ScorePicker
        label="Effort"
        value={2}
        onChange={onChange}
        tone="effort"
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Effort 4 of 5' }))
    expect(onChange).toHaveBeenCalledWith(4)
  })
})

import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// RTL's auto-cleanup detects a global `afterEach`; this repo keeps
// `test.globals` off (tests import from 'vitest' explicitly), so it has
// to be wired up by hand here instead.
afterEach(() => {
  cleanup()
})

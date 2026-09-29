import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// RTL's auto-cleanup detects a global `afterEach`; this repo keeps
// `test.globals` off (tests import from 'vitest' explicitly), so it has
// to be wired up by hand here instead.
afterEach(() => {
  cleanup()
})

// Same story for the act environment: RTL sets IS_REACT_ACT_ENVIRONMENT
// in a global `beforeAll`, which never registers with globals off. RTL's
// own `act` sets it per call, so RTL-based tests were fine, but
// `src/lib/render-hook.tsx` calls React's `act` directly and React warns
// that the environment isn't configured for act(...) on every call.
;(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
).IS_REACT_ACT_ENVIRONMENT = true

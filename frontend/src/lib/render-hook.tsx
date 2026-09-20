import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import type { ComponentType, ReactNode } from 'react'

/**
 * Minimal hand-rolled `renderHook`, not React Testing Library: enough to
 * mount a hook (optionally under a Provider `wrapper`) with real
 * createRoot + act, and read its latest return value. Intentionally has
 * no query/fireEvent API; this is for exercising store/auth hook logic
 * in non-UI tests, not for testing rendered output.
 */
export function renderHook<T>(
  useHook: () => T,
  options: { wrapper?: ComponentType<{ children: ReactNode }> } = {},
) {
  let value: T
  function Harness() {
    value = useHook()
    return null
  }

  const Wrapper = options.wrapper
  const element = Wrapper ? (
    <Wrapper>
      <Harness />
    </Wrapper>
  ) : (
    <Harness />
  )

  const container = document.createElement('div')
  document.body.appendChild(container)
  let root: Root
  act(() => {
    root = createRoot(container)
    root.render(element)
  })

  return {
    get result() {
      return value
    },
    unmount() {
      act(() => {
        root.unmount()
      })
      container.remove()
    },
  }
}

export { act }

/**
 * Flushes pending microtasks (and one macrotask tick) inside `act`, so
 * state updates from an already-in-flight promise (e.g. the fetch a
 * provider kicked off on mount) land before assertions run.
 */
export async function flush(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
}

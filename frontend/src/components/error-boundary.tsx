import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/empty-state'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
}

/**
 * Catches render-time errors anywhere below it so a crash shows this
 * fallback instead of a white screen. componentDidCatch is also the spot
 * to forward errors to real error tracking once that's wired up (see
 * _docs/tech-debt.md, Sentry is deferred to the deploy phase); for now
 * console.error is the only record.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Unhandled render error:', error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="grid min-h-dvh place-items-center px-4">
          <EmptyState
            variant="page"
            icon={AlertTriangle}
            tone="danger"
            title="Something went wrong"
            message="The app hit an unexpected error. Reloading usually fixes it."
            action={
              <Button size="lg" onClick={() => window.location.assign('/')}>
                Reload
              </Button>
            }
          />
        </div>
      )
    }

    return this.props.children
  }
}

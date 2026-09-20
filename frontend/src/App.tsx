import { useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { useAuth } from '@/use-auth'
import { StoreProvider } from '@/store'
import { AppHeader } from '@/components/layout/app-header'
import { ErrorBoundary } from '@/components/error-boundary'
import { QuickCaptureDialog } from '@/components/quick-capture-dialog'
import { Toaster } from '@/components/ui/toaster'
import { DashboardPage } from '@/pages/dashboard'
import { ProjectDetailPage } from '@/pages/project-detail'
import { NotFoundPage } from '@/pages/not-found'
import { LoginPage } from '@/pages/login'
import { SignupPage } from '@/pages/signup'

export function App() {
  const { status } = useAuth()

  return (
    <ErrorBoundary>
      {status === 'loading' ? (
        <div className="grid min-h-dvh place-items-center">
          <Loader2 className="size-6 animate-spin text-muted-foreground" />
        </div>
      ) : status === 'unauthenticated' ? (
        <Routes>
          <Route path="/signup" element={<SignupPage />} />
          <Route path="*" element={<LoginPage />} />
        </Routes>
      ) : (
        // Mounting StoreProvider only once authenticated ensures its
        // project state (and the fetch-on-mount that populates it)
        // starts fresh for each signed-in user, and never fires while
        // logged out.
        <StoreProvider>
          <AuthenticatedApp />
        </StoreProvider>
      )}
      <Toaster />
    </ErrorBoundary>
  )
}

function AuthenticatedApp() {
  const [captureOpen, setCaptureOpen] = useState(false)

  return (
    <div className="min-h-dvh bg-background">
      <AppHeader onCapture={() => setCaptureOpen(true)} />
      <main className="mx-auto w-full max-w-6xl px-4 pb-24 pt-6 sm:px-6">
        <Routes>
          <Route
            path="/"
            element={<DashboardPage onCapture={() => setCaptureOpen(true)} />}
          />
          <Route path="/project/:id" element={<ProjectDetailPage />} />
          <Route path="/login" element={<Navigate to="/" replace />} />
          <Route path="/signup" element={<Navigate to="/" replace />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </main>
      <QuickCaptureDialog
        open={captureOpen}
        onClose={() => setCaptureOpen(false)}
      />
    </div>
  )
}

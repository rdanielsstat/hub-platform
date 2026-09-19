import { useState } from 'react'
import { Route, Routes } from 'react-router-dom'
import { AppHeader } from '@/components/layout/app-header'
import { QuickCaptureDialog } from '@/components/quick-capture-dialog'
import { DashboardPage } from '@/pages/dashboard'
import { ProjectDetailPage } from '@/pages/project-detail'
import { NotFoundPage } from '@/pages/not-found'

export function App() {
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

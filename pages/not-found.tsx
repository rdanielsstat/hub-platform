import { Link } from 'react-router-dom'
import { Compass } from 'lucide-react'
import { buttonVariants } from '@/components/ui/button'

export function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-24 text-center">
      <div className="grid size-12 place-items-center rounded-2xl bg-muted text-muted-foreground">
        <Compass className="size-6" />
      </div>
      <div className="space-y-1">
        <h1 className="text-lg font-semibold">Nothing parked here</h1>
        <p className="text-sm text-muted-foreground">
          This page doesn&apos;t exist. Head back to the hub.
        </p>
      </div>
      <Link to="/" className={buttonVariants({ size: 'lg' })}>
        Back to dashboard
      </Link>
    </div>
  )
}

import { Link } from 'react-router-dom'
import { Compass } from 'lucide-react'
import { buttonVariants } from '@/components/ui/button-variants'
import { EmptyState } from '@/components/ui/empty-state'

export function NotFoundPage() {
  return (
    <EmptyState
      variant="page"
      icon={Compass}
      title="Nothing parked here"
      message="This page doesn't exist. Head back to the hub."
      action={
        <Link to="/" className={buttonVariants({ size: 'lg' })}>
          Back to dashboard
        </Link>
      }
    />
  )
}

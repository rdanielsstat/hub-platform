import { useEffect, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'

interface DialogProps {
  open: boolean
  onClose: () => void
  children: ReactNode
  className?: string
  /** accessible title for the dialog */
  title?: string
}

function Dialog({ open, onClose, children, className, title }: DialogProps) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [open, onClose])

  if (!open) return null

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-end justify-center sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm animate-in fade-in-0"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        className={cn(
          'relative z-10 flex max-h-[92vh] w-full flex-col overflow-hidden rounded-t-2xl border border-border bg-card shadow-lg',
          'sm:max-w-lg sm:rounded-2xl',
          'animate-in fade-in-0 zoom-in-95 slide-in-from-bottom-4 sm:slide-in-from-bottom-0',
          className,
        )}
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute right-3 top-3 z-20 grid size-7 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          aria-label="Close"
        >
          <X className="size-4" />
        </button>
        {children}
      </div>
    </div>,
    document.body,
  )
}

function DialogHeader({
  title,
  description,
}: {
  title: string
  description?: string
}) {
  return (
    <div className="flex flex-col gap-1 border-b border-border px-5 py-4 pr-12">
      <h2 className="text-base font-semibold tracking-tight">{title}</h2>
      {description ? (
        <p className="text-sm text-muted-foreground">{description}</p>
      ) : null}
    </div>
  )
}

function DialogBody({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn('overflow-y-auto px-5 py-4', className)}>{children}</div>
  )
}

function DialogFooter({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex items-center justify-end gap-2 border-t border-border px-5 py-3',
        className,
      )}
    >
      {children}
    </div>
  )
}

export { Dialog, DialogHeader, DialogBody, DialogFooter }

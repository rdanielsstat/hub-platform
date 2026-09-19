import type { ReactNode } from 'react'
import { Dialog as BaseDialog } from '@base-ui/react/dialog'
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
  return (
    <BaseDialog.Root
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose()
      }}
    >
      <BaseDialog.Portal>
        <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
          <BaseDialog.Backdrop className="fixed inset-0 bg-black/40 backdrop-blur-sm transition-opacity data-[ending-style]:opacity-0 data-[starting-style]:opacity-0" />
          <BaseDialog.Popup
            aria-label={title}
            initialFocus={false}
            className={cn(
              'relative z-10 flex max-h-[92vh] w-full flex-col overflow-hidden rounded-t-2xl border border-border bg-card shadow-lg transition-all',
              'sm:max-w-lg sm:rounded-2xl',
              'data-[starting-style]:translate-y-4 data-[starting-style]:opacity-0 sm:data-[starting-style]:translate-y-0 sm:data-[starting-style]:scale-95',
              'data-[ending-style]:translate-y-4 data-[ending-style]:opacity-0 sm:data-[ending-style]:translate-y-0 sm:data-[ending-style]:scale-95',
              className,
            )}
          >
            <BaseDialog.Close
              aria-label="Close"
              className="absolute right-3 top-3 z-20 grid size-7 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <X className="size-4" />
            </BaseDialog.Close>
            {children}
          </BaseDialog.Popup>
        </div>
      </BaseDialog.Portal>
    </BaseDialog.Root>
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

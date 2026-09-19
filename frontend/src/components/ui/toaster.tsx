import { Toast } from '@base-ui/react/toast'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { toastManager } from '@/lib/toast'

function ToastList() {
  const { toasts } = Toast.useToastManager()

  return (
    <Toast.Portal>
      <Toast.Viewport className="fixed inset-x-4 bottom-4 z-50 flex flex-col items-center gap-2 sm:inset-x-auto sm:right-4 sm:items-end">
        {toasts.map((toast) => (
          <Toast.Root
            key={toast.id}
            toast={toast}
            className={cn(
              'relative flex w-full max-w-sm items-start gap-3 rounded-xl border border-border bg-card p-4 pr-9 shadow-lg transition-all',
              'data-[type=error]:border-rose-500/30',
              'data-[starting-style]:translate-y-2 data-[starting-style]:opacity-0',
              'data-[ending-style]:opacity-0',
            )}
          >
            <Toast.Content className="flex-1">
              {toast.title ? (
                <Toast.Title className="text-sm font-medium text-foreground">
                  {toast.title}
                </Toast.Title>
              ) : null}
              {toast.description ? (
                <Toast.Description className="mt-0.5 text-xs text-muted-foreground">
                  {toast.description}
                </Toast.Description>
              ) : null}
            </Toast.Content>
            <Toast.Close
              aria-label="Dismiss"
              className="absolute right-2 top-2 grid size-6 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <X className="size-3.5" />
            </Toast.Close>
          </Toast.Root>
        ))}
      </Toast.Viewport>
    </Toast.Portal>
  )
}

export function Toaster() {
  return (
    <Toast.Provider toastManager={toastManager}>
      <ToastList />
    </Toast.Provider>
  )
}

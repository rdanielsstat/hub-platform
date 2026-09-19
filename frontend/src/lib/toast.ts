import { Toast } from '@base-ui/react/toast'

/**
 * A manager usable outside React (from the store, not just components),
 * so any write path can surface a failure the same way. `Toaster`
 * (components/ui/toaster.tsx) renders whatever's added here.
 */
export const toastManager = Toast.createToastManager()

export function notifyError(message: string): void {
  toastManager.add({ title: message, type: 'error', timeout: 6000 })
}

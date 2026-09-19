import { useContext } from 'react'
import { StoreContext, type StoreValue } from '@/store-context'

export function useStore(): StoreValue {
  const ctx = useContext(StoreContext)
  if (!ctx) throw new Error('useStore must be used within a StoreProvider')
  return ctx
}

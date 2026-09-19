import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { LogOut, Moon, Plus, Sun } from 'lucide-react'
import { useAuth } from '@/use-auth'
import { Button } from '@/components/ui/button'

function useTheme() {
  const [dark, setDark] = useState(false)
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
  }, [dark])
  return { dark, toggle: () => setDark((d) => !d) }
}

export function AppHeader({ onCapture }: { onCapture: () => void }) {
  const { dark, toggle } = useTheme()
  const { user, logout } = useAuth()

  return (
    <header className="sticky top-0 z-30 border-b border-border/80 bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between gap-3 px-4 sm:px-6">
        <Link to="/" className="flex flex-col leading-none">
          <span className="text-[0.95rem] font-semibold tracking-tight">
            hub
          </span>
          <span className="hidden text-[0.7rem] text-muted-foreground sm:block">
            capture · triage · graduate
          </span>
        </Link>

        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={toggle}
            aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {dark ? <Sun /> : <Moon />}
          </Button>
          <Button size="sm" onClick={onCapture}>
            <Plus />
            <span className="hidden sm:inline">Quick capture</span>
            <span className="sm:hidden">Capture</span>
          </Button>
          <div className="ml-1 flex items-center gap-1.5 border-l border-border pl-2">
            <span className="hidden max-w-28 truncate text-xs text-muted-foreground sm:inline">
              {user?.displayName || user?.email}
            </span>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={logout}
              aria-label="Sign out"
            >
              <LogOut />
            </Button>
          </div>
        </div>
      </div>
    </header>
  )
}

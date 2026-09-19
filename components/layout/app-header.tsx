import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Moon, Plus, Sun } from 'lucide-react'
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

  return (
    <header className="sticky top-0 z-30 border-b border-border/80 bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between gap-3 px-4 sm:px-6">
        <Link to="/" className="flex items-center gap-2.5">
          <span className="grid size-7 place-items-center rounded-lg bg-primary text-sm font-bold text-primary-foreground">
            h
          </span>
          <div className="flex flex-col leading-none">
            <span className="text-[0.95rem] font-semibold tracking-tight">
              hub
            </span>
            <span className="hidden text-[0.7rem] text-muted-foreground sm:block">
              capture · triage · graduate
            </span>
          </div>
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
        </div>
      </div>
    </header>
  )
}

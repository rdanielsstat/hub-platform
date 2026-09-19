import { useEffect, useState } from 'react'
import { Trash2 } from 'lucide-react'
import { api, type Note } from '@/services/api'
import { useStore } from '@/use-store'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { formatRelative } from '@/lib/project-utils'

export function NotesPanel({ projectId }: { projectId: string }) {
  const { addNote, deleteNote } = useStore()
  const [notes, setNotes] = useState<Note[]>([])
  const [loading, setLoading] = useState(true)
  const [body, setBody] = useState('')
  const [saving, setSaving] = useState(false)
  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional: resets the loading flag before an async listNotes() fetch whenever projectId changes; can't be derived during render.
    setLoading(true)
    void api.listNotes(projectId).then((data) => {
      if (active) {
        setNotes(data)
        setLoading(false)
      }
    })
    return () => {
      active = false
    }
  }, [projectId])

  async function add() {
    const text = body.trim()
    if (!text) return
    setSaving(true)
    try {
      const note = await addNote(projectId, text)
      setNotes((prev) => [note, ...prev])
      setBody('')
    } catch {
      // store already showed a toast; keep the draft so nothing is lost
    } finally {
      setSaving(false)
    }
  }

  async function remove(id: string) {
    setConfirmingId(null)
    setDeletingId(id)
    try {
      await deleteNote(id)
      setNotes((prev) => prev.filter((n) => n.id !== id))
    } catch {
      // store already showed a toast; the note wasn't actually deleted,
      // so it stays in the list rather than disappearing and reappearing
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2">
        <Textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Add a note, thought, or update…"
          rows={3}
          onKeyDown={(e) => {
            if (
              (e.metaKey || e.ctrlKey) &&
              e.key === 'Enter' &&
              !e.nativeEvent.isComposing
            ) {
              e.preventDefault()
              void add()
            }
          }}
        />
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">⌘/Ctrl + Enter</span>
          <Button size="sm" onClick={add} disabled={!body.trim() || saving}>
            Add note
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 2 }).map((_, i) => (
            <div
              key={i}
              className="h-16 animate-pulse rounded-lg bg-muted/50"
            />
          ))}
        </div>
      ) : notes.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">
          No notes yet.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {notes.map((note) => (
            <li
              key={note.id}
              className="group rounded-lg border border-border bg-card p-3"
            >
              <p className="whitespace-pre-wrap text-sm leading-relaxed">
                {note.body}
              </p>
              <div className="mt-2 flex items-center justify-between">
                {confirmingId === note.id ? (
                  <>
                    <span className="text-xs text-muted-foreground">
                      Delete this note?
                    </span>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setConfirmingId(null)}
                      >
                        Cancel
                      </Button>
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={() => remove(note.id)}
                        disabled={deletingId === note.id}
                      >
                        Delete
                      </Button>
                    </div>
                  </>
                ) : (
                  <>
                    <span className="text-xs text-muted-foreground">
                      {formatRelative(note.createdAt)}
                    </span>
                    <button
                      type="button"
                      onClick={() => setConfirmingId(note.id)}
                      aria-label="Delete note"
                      className="text-muted-foreground opacity-0 transition-opacity hover:text-rose-500 group-hover:opacity-100"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

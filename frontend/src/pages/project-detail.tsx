import { useLayoutEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowLeft,
  ArrowUpRight,
  Compass,
  Plus,
  Trash2,
  X,
  Zap,
} from 'lucide-react'
import { useStore } from '@/use-store'
import { STATUSES, type Link as ProjectLink, type Status } from '@/services/api'
import { StatusBadge } from '@/components/status-badge'
import { NotesPanel } from '@/components/detail/notes-panel'
import { ScorePicker } from '@/components/score-meter'
import { Button } from '@/components/ui/button'
import { buttonVariants } from '@/components/ui/button-variants'
import { Card } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { formatDate, formatRelative, isSafeLinkUrl } from '@/lib/project-utils'
import {
  DESCRIPTION_MAX_LENGTH,
  LINK_LABEL_MAX_LENGTH,
  LINK_URL_MAX_LENGTH,
  NEXT_ACTION_MAX_LENGTH,
  PITCH_MAX_LENGTH,
  PROJECT_NAME_MAX_LENGTH,
  TAG_MAX_LENGTH,
} from '@/lib/limits'

export function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { loading, error, refresh, getProject, updateProject, deleteProject } =
    useStore()
  const project = id ? getProject(id) : undefined

  const [name, setName] = useState('')
  const [pitch, setPitch] = useState('')
  const [description, setDescription] = useState('')
  const [nextAction, setNextAction] = useState('')
  const [tagInput, setTagInput] = useState('')
  const [linkLabelInput, setLinkLabelInput] = useState('')
  const [linkInput, setLinkInput] = useState('')
  const [confirmingDelete, setConfirmingDelete] = useState(false)

  // Re-seed the editable draft fields when the loaded project changes,
  // adjusted during render (see https://react.dev/learn/you-might-not-need-an-effect#adjusting-some-state-when-a-prop-changes)
  // instead of via an effect, since the fields must stay independently
  // editable afterwards rather than track `project` on every render.
  const [seededId, setSeededId] = useState<string | undefined>(undefined)
  if (project && project.id !== seededId) {
    setSeededId(project.id)
    setName(project.name)
    setPitch(project.pitch)
    setDescription(project.description)
    setNextAction(project.nextAction)
  }

  // Grow the next-action textarea to fit its wrapped content instead of
  // clipping it, by syncing the DOM height to scrollHeight after each change.
  const nextActionRef = useRef<HTMLTextAreaElement>(null)
  useLayoutEffect(() => {
    const el = nextActionRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [nextAction])

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-40 animate-pulse rounded-lg bg-muted/50" />
        <div className="h-32 animate-pulse rounded-xl bg-muted/40" />
        <div className="h-64 animate-pulse rounded-xl bg-muted/40" />
      </div>
    )
  }

  if (!project || !id) {
    // Distinguish "the load itself failed" from "this id genuinely
    // doesn't exist" — same underlying bug the dashboard's load-error
    // state fixes, surfaced here too since it's the same store `error`.
    if (error) {
      return (
        <EmptyState
          variant="page"
          icon={AlertTriangle}
          tone="danger"
          title="Couldn't load this idea"
          message={error}
          action={
            <Button size="lg" onClick={() => void refresh()}>
              Try again
            </Button>
          }
        />
      )
    }
    return (
      <EmptyState
        variant="page"
        icon={Compass}
        title="Idea not found"
        message="It may have been deleted. Head back to the hub."
        action={
          <Link to="/" className={buttonVariants({ size: 'lg' })}>
            Back to dashboard
          </Link>
        }
      />
    )
  }

  // Returns whether the save succeeded. The store already reports the
  // error (toast); callers only need this to know whether to revert
  // local draft state that isn't otherwise controlled by `project`.
  async function save(
    patch: Parameters<typeof updateProject>[1],
  ): Promise<boolean> {
    try {
      await updateProject(id!, patch)
      return true
    } catch {
      return false
    }
  }

  function addTag() {
    const tag = tagInput.trim().toLowerCase()
    if (!tag || project!.tags.includes(tag)) {
      setTagInput('')
      return
    }
    void save({ tags: [...project!.tags, tag] })
    setTagInput('')
  }

  function removeTag(tag: string) {
    void save({ tags: project!.tags.filter((t) => t !== tag) })
  }

  function addLink() {
    const url = linkInput.trim()
    if (!url) return
    const normalized = /^https?:\/\//i.test(url) ? url : `https://${url}`
    const label = linkLabelInput.trim()
    const link: ProjectLink = label
      ? { label, url: normalized }
      : { url: normalized }
    void save({ links: [...project!.links, link] })
    setLinkLabelInput('')
    setLinkInput('')
  }

  function removeLink(url: string) {
    void save({ links: project!.links.filter((l) => l.url !== url) })
  }

  async function handleDelete() {
    try {
      await deleteProject(id!)
      navigate('/')
    } catch {
      // store already showed a toast; let them retry from a clean state
      setConfirmingDelete(false)
    }
  }

  return (
    <div className="flex flex-col gap-6 pb-10">
      <div className="flex items-center justify-between gap-3">
        <Link
          to="/"
          className={cn(
            buttonVariants({ variant: 'ghost', size: 'sm' }),
            'text-muted-foreground hover:text-foreground',
          )}
        >
          <ArrowLeft className="size-4" />
          All ideas
        </Link>
        {confirmingDelete ? (
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">
              Delete this idea?
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setConfirmingDelete(false)}
            >
              Cancel
            </Button>
            <Button variant="destructive" size="sm" onClick={handleDelete}>
              Delete
            </Button>
          </div>
        ) : (
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Delete idea"
            onClick={() => setConfirmingDelete(true)}
          >
            <Trash2 />
          </Button>
        )}
      </div>

      {/* Next action: the single most important thing on this page */}
      <div className="flex flex-col gap-2 rounded-xl border border-primary/20 bg-accent/60 p-4">
        <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-accent-foreground">
          <Zap className="size-3.5" />
          Next action
        </div>
        <textarea
          ref={nextActionRef}
          rows={1}
          maxLength={NEXT_ACTION_MAX_LENGTH}
          value={nextAction}
          onChange={(e) => setNextAction(e.target.value)}
          onBlur={async () => {
            if (nextAction === project.nextAction) return
            const ok = await save({ nextAction })
            if (!ok) setNextAction(project.nextAction)
          }}
          placeholder="The single next concrete step…"
          className="flex w-full min-w-0 resize-none overflow-hidden rounded-lg border border-transparent bg-transparent px-0 py-1 text-base font-medium leading-snug shadow-none outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:bg-background focus-visible:px-3 focus-visible:ring-3 focus-visible:ring-ring/40 disabled:cursor-not-allowed disabled:opacity-50"
        />
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <Input
            value={name}
            maxLength={PROJECT_NAME_MAX_LENGTH}
            onChange={(e) => setName(e.target.value)}
            onBlur={async () => {
              const trimmed = name.trim()
              if (!trimmed || trimmed === project.name) return
              const ok = await save({ name: trimmed })
              if (!ok) setName(project.name)
            }}
            className="h-auto border-transparent bg-transparent px-0 text-2xl font-semibold tracking-tight shadow-none focus-visible:border-ring focus-visible:bg-background focus-visible:px-3"
          />
          <Select
            value={project.status}
            onChange={(e) => save({ status: e.target.value as Status })}
            className="h-9 w-40 shrink-0"
            aria-label="Status"
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <StatusBadge status={project.status} />
          <span>Updated {formatRelative(project.updatedAt)}</span>
        </div>
        <Input
          value={pitch}
          maxLength={PITCH_MAX_LENGTH}
          onChange={(e) => setPitch(e.target.value)}
          onBlur={async () => {
            if (pitch === project.pitch) return
            const ok = await save({ pitch })
            if (!ok) setPitch(project.pitch)
          }}
          placeholder="One-line pitch: the scannable version"
          className="border-transparent bg-transparent px-0 text-sm text-muted-foreground shadow-none focus-visible:border-ring focus-visible:bg-background focus-visible:px-3"
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          <section className="flex flex-col gap-2">
            <Label htmlFor="description">Description</Label>
            <Textarea
              id="description"
              rows={6}
              maxLength={DESCRIPTION_MAX_LENGTH}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              onBlur={async () => {
                if (description === project.description) return
                const ok = await save({ description })
                if (!ok) setDescription(project.description)
              }}
              placeholder="The full brain-dump…"
            />
          </section>

          <section className="flex flex-col gap-2">
            <Label>Notes</Label>
            <NotesPanel projectId={id} />
          </section>
        </div>

        <div className="flex flex-col gap-6">
          <Card className="flex flex-col gap-4 p-4">
            <ScorePicker
              label="Excitement"
              value={project.excitement}
              onChange={(v) => save({ excitement: v })}
              tone="excitement"
            />
            <ScorePicker
              label="Potential"
              value={project.potential}
              onChange={(v) => save({ potential: v })}
              tone="potential"
            />
            <ScorePicker
              label="Effort"
              value={project.effort}
              onChange={(v) => save({ effort: v })}
              tone="effort"
            />
          </Card>

          <Card className="flex flex-col gap-2 p-4">
            <Label htmlFor="target-date">Target date</Label>
            <Input
              id="target-date"
              type="date"
              value={project.targetDate ?? ''}
              onChange={(e) => save({ targetDate: e.target.value || null })}
            />
            {project.targetDate ? (
              <p className="text-xs text-muted-foreground">
                {formatDate(project.targetDate)}
              </p>
            ) : null}
          </Card>

          <Card className="flex flex-col gap-2 p-4">
            <Label>Tags</Label>
            <div className="flex flex-wrap gap-1.5">
              {project.tags.map((tag) => (
                <span
                  key={tag}
                  className="group inline-flex items-center gap-1 rounded-md bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground"
                >
                  #{tag}
                  <button
                    type="button"
                    aria-label={`Remove tag ${tag}`}
                    onClick={() => removeTag(tag)}
                    className="text-muted-foreground/60 transition-colors hover:text-rose-500"
                  >
                    <X className="size-3" />
                  </button>
                </span>
              ))}
              {project.tags.length === 0 ? (
                <p className="text-xs text-muted-foreground">No tags yet.</p>
              ) : null}
            </div>
            <div className="flex gap-2">
              <Input
                value={tagInput}
                maxLength={TAG_MAX_LENGTH}
                onChange={(e) => setTagInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    addTag()
                  }
                }}
                placeholder="Add a tag…"
                className="h-8"
              />
              <Button
                variant="outline"
                size="icon-sm"
                aria-label="Add tag"
                onClick={addTag}
                disabled={!tagInput.trim()}
              >
                <Plus />
              </Button>
            </div>
          </Card>

          <Card className="flex flex-col gap-2 p-4">
            <Label>Links</Label>
            {project.links.length > 0 ? (
              <ul className="flex flex-col gap-1">
                {project.links.map((link) => (
                  <li
                    key={link.url}
                    className="group flex items-center justify-between gap-2 rounded-md px-1.5 py-1 text-sm hover:bg-muted"
                  >
                    {isSafeLinkUrl(link.url) ? (
                      <a
                        href={link.url}
                        target="_blank"
                        rel="noreferrer"
                        className="flex min-w-0 items-center gap-1.5 truncate text-primary"
                      >
                        <ArrowUpRight className="size-3.5 shrink-0" />
                        <span className="truncate">
                          {link.label || link.url}
                        </span>
                      </a>
                    ) : (
                      // Not http(s): shown as plain text, never a link.
                      <span
                        title="Not an http(s) link, so it isn't clickable"
                        className="min-w-0 truncate text-muted-foreground"
                      >
                        {link.label || link.url}
                      </span>
                    )}
                    <button
                      type="button"
                      aria-label={`Remove link ${link.label || link.url}`}
                      onClick={() => removeLink(link.url)}
                      className="shrink-0 text-muted-foreground opacity-0 transition-opacity hover:text-rose-500 group-hover:opacity-100"
                    >
                      <X className="size-3.5" />
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-muted-foreground">No links yet.</p>
            )}
            <div className="flex gap-2">
              <Input
                value={linkLabelInput}
                maxLength={LINK_LABEL_MAX_LENGTH}
                onChange={(e) => setLinkLabelInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    addLink()
                  }
                }}
                placeholder="Label (optional)"
                className="h-8 w-28 shrink-0"
              />
              <Input
                value={linkInput}
                maxLength={LINK_URL_MAX_LENGTH}
                onChange={(e) => setLinkInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    addLink()
                  }
                }}
                placeholder="https://…"
                className="h-8"
              />
              <Button
                variant="outline"
                size="icon-sm"
                aria-label="Add link"
                onClick={addLink}
                disabled={!linkInput.trim()}
              >
                <Plus />
              </Button>
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}

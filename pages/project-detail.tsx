import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  ArrowUpRight,
  Compass,
  Plus,
  Trash2,
  X,
  Zap,
} from 'lucide-react'
import { useStore } from '@/use-store'
import { STATUSES, type Status } from '@/services/api'
import { StatusBadge } from '@/components/status-badge'
import { RatingInput } from '@/components/detail/rating-input'
import { NotesPanel } from '@/components/detail/notes-panel'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { formatDate, formatRelative } from '@/lib/project-utils'

export function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { loading, getProject, updateProject, deleteProject } = useStore()
  const project = id ? getProject(id) : undefined

  const [name, setName] = useState('')
  const [pitch, setPitch] = useState('')
  const [description, setDescription] = useState('')
  const [nextAction, setNextAction] = useState('')
  const [tagInput, setTagInput] = useState('')
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

  const due = useMemo(
    () => (project ? formatDate(project.targetDate) : '-'),
    [project],
  )

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
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-24 text-center">
        <div className="grid size-12 place-items-center rounded-2xl bg-muted text-muted-foreground">
          <Compass className="size-6" />
        </div>
        <div className="space-y-1">
          <h1 className="text-lg font-semibold">Idea not found</h1>
          <p className="text-sm text-muted-foreground">
            It may have been deleted. Head back to the hub.
          </p>
        </div>
        <Link
          to="/"
          className="inline-flex h-9 items-center rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground"
        >
          Back to dashboard
        </Link>
      </div>
    )
  }

  async function save(patch: Parameters<typeof updateProject>[1]) {
    await updateProject(id!, patch)
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
    void save({ links: [...project!.links, normalized] })
    setLinkInput('')
  }

  function removeLink(url: string) {
    void save({ links: project!.links.filter((l) => l !== url) })
  }

  async function handleDelete() {
    await deleteProject(id!)
    navigate('/')
  }

  return (
    <div className="flex flex-col gap-6 pb-10">
      <div className="flex items-center justify-between gap-3">
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
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
        <Input
          value={nextAction}
          onChange={(e) => setNextAction(e.target.value)}
          onBlur={() => save({ nextAction })}
          placeholder="The single next concrete step…"
          className="border-transparent bg-transparent px-0 text-base font-medium shadow-none focus-visible:border-ring focus-visible:bg-background focus-visible:px-3"
        />
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            onBlur={() => name.trim() && save({ name: name.trim() })}
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
          onChange={(e) => setPitch(e.target.value)}
          onBlur={() => save({ pitch })}
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
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              onBlur={() => save({ description })}
              placeholder="The full brain-dump…"
            />
          </section>

          <section className="flex flex-col gap-2">
            <Label>Notes</Label>
            <NotesPanel projectId={id} />
          </section>
        </div>

        <div className="flex flex-col gap-6">
          <section className="flex flex-col gap-4 rounded-xl border border-border bg-card p-4">
            <RatingInput
              label="Excitement"
              value={project.excitement}
              onChange={(v) => save({ excitement: v })}
              accent="bg-primary"
            />
            <RatingInput
              label="Potential"
              value={project.potential}
              onChange={(v) => save({ potential: v })}
              accent="bg-emerald-500"
            />
            <RatingInput
              label="Effort"
              value={project.effort}
              onChange={(v) => save({ effort: v })}
              accent="bg-amber-500"
            />
          </section>

          <section className="flex flex-col gap-2 rounded-xl border border-border bg-card p-4">
            <Label htmlFor="target-date">Target date</Label>
            <Input
              id="target-date"
              type="date"
              value={project.targetDate ?? ''}
              onChange={(e) => save({ targetDate: e.target.value || null })}
            />
            {project.targetDate ? (
              <p className="text-xs text-muted-foreground">{due}</p>
            ) : null}
          </section>

          <section className="flex flex-col gap-2 rounded-xl border border-border bg-card p-4">
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
          </section>

          <section className="flex flex-col gap-2 rounded-xl border border-border bg-card p-4">
            <Label>Links</Label>
            {project.links.length > 0 ? (
              <ul className="flex flex-col gap-1">
                {project.links.map((link) => (
                  <li
                    key={link}
                    className="group flex items-center justify-between gap-2 rounded-md px-1.5 py-1 text-sm hover:bg-muted"
                  >
                    <a
                      href={link}
                      target="_blank"
                      rel="noreferrer"
                      className="flex min-w-0 items-center gap-1.5 truncate text-primary"
                    >
                      <ArrowUpRight className="size-3.5 shrink-0" />
                      <span className="truncate">{link}</span>
                    </a>
                    <button
                      type="button"
                      aria-label={`Remove link ${link}`}
                      onClick={() => removeLink(link)}
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
                value={linkInput}
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
          </section>
        </div>
      </div>
    </div>
  )
}

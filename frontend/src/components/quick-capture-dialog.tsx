import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronDown, Loader2 } from 'lucide-react'
import {
  Dialog,
  DialogBody,
  DialogFooter,
  DialogHeader,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select } from '@/components/ui/select'
import { ScorePicker } from '@/components/score-meter'
import { useStore } from '@/use-store'
import { STATUSES, type Status } from '@/services/api'
import { cn } from '@/lib/utils'
import {
  DESCRIPTION_MAX_LENGTH,
  NEXT_ACTION_MAX_LENGTH,
  PITCH_MAX_LENGTH,
  PROJECT_NAME_MAX_LENGTH,
  TAG_LIST_INPUT_MAX_LENGTH,
} from '@/lib/limits'

interface Props {
  open: boolean
  onClose: () => void
}

const empty = {
  name: '',
  pitch: '',
  description: '',
  status: 'Inbox' as Status,
  tags: '',
  nextAction: '',
  excitement: 3,
  effort: 3,
  potential: 3,
}

export function QuickCaptureDialog({ open, onClose }: Props) {
  const { createProject } = useStore()
  const navigate = useNavigate()
  const [form, setForm] = useState(empty)
  const [expanded, setExpanded] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  function reset() {
    setForm(empty)
    setExpanded(false)
    setSubmitting(false)
  }

  function handleClose() {
    reset()
    onClose()
  }

  async function handleSubmit(goToDetail: boolean) {
    if (!form.name.trim() || submitting) return
    setSubmitting(true)
    try {
      const created = await createProject({
        name: form.name,
        pitch: form.pitch,
        description: form.description,
        status: form.status,
        tags: form.tags
          .split(',')
          .map((t) => t.trim().toLowerCase())
          .filter(Boolean),
        nextAction: form.nextAction,
        excitement: form.excitement,
        effort: form.effort,
        potential: form.potential,
      })
      reset()
      onClose()
      if (goToDetail) navigate(`/project/${created.id}`)
    } catch {
      // store already showed a toast; leave the dialog open with the
      // form data intact so nothing typed is lost
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onClose={handleClose} title="Quick capture">
      <DialogHeader
        title="Quick capture"
        description="Get it out of your head. Only a name is required."
      />
      <DialogBody className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="qc-name">Name</Label>
          <Input
            id="qc-name"
            maxLength={PROJECT_NAME_MAX_LENGTH}
            autoFocus
            placeholder="e.g. Chess improvement analytics"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            onKeyDown={(e) => {
              if (
                e.key === 'Enter' &&
                !e.nativeEvent.isComposing &&
                e.keyCode !== 229
              ) {
                e.preventDefault()
                void handleSubmit(false)
              }
            }}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="qc-pitch">One-line pitch</Label>
          <Input
            id="qc-pitch"
            maxLength={PITCH_MAX_LENGTH}
            placeholder="The scannable version"
            value={form.pitch}
            onChange={(e) => setForm({ ...form, pitch: e.target.value })}
          />
        </div>

        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex w-fit items-center gap-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
        >
          <ChevronDown
            className={cn(
              'size-3.5 transition-transform',
              expanded && 'rotate-180',
            )}
          />
          {expanded ? 'Fewer details' : 'More details'}
        </button>

        {expanded ? (
          <div className="flex flex-col gap-4 border-t border-border pt-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="qc-desc">Brain dump</Label>
              <Textarea
                id="qc-desc"
                maxLength={DESCRIPTION_MAX_LENGTH}
                placeholder="Everything you're thinking about this…"
                value={form.description}
                onChange={(e) =>
                  setForm({ ...form, description: e.target.value })
                }
              />
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="qc-status">Status</Label>
                <Select
                  id="qc-status"
                  value={form.status}
                  onChange={(e) =>
                    setForm({ ...form, status: e.target.value as Status })
                  }
                >
                  {STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="qc-tags">Tags</Label>
                <Input
                  id="qc-tags"
                  maxLength={TAG_LIST_INPUT_MAX_LENGTH}
                  placeholder="stats, chess"
                  value={form.tags}
                  onChange={(e) => setForm({ ...form, tags: e.target.value })}
                />
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="qc-next">Next action</Label>
              <Input
                id="qc-next"
                maxLength={NEXT_ACTION_MAX_LENGTH}
                placeholder="The single next concrete step"
                value={form.nextAction}
                onChange={(e) =>
                  setForm({ ...form, nextAction: e.target.value })
                }
              />
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <ScorePicker
                label="Excitement"
                tone="excitement"
                value={form.excitement}
                onChange={(v) => setForm({ ...form, excitement: v })}
              />
              <ScorePicker
                label="Potential"
                tone="potential"
                value={form.potential}
                onChange={(v) => setForm({ ...form, potential: v })}
              />
              <ScorePicker
                label="Effort"
                tone="effort"
                value={form.effort}
                onChange={(v) => setForm({ ...form, effort: v })}
              />
            </div>
          </div>
        ) : null}
      </DialogBody>
      <DialogFooter>
        <Button variant="ghost" size="lg" onClick={handleClose}>
          Cancel
        </Button>
        <Button
          variant="outline"
          size="lg"
          disabled={!form.name.trim() || submitting}
          onClick={() => handleSubmit(true)}
        >
          Capture & open
        </Button>
        <Button
          size="lg"
          disabled={!form.name.trim() || submitting}
          onClick={() => handleSubmit(false)}
        >
          {submitting ? <Loader2 className="animate-spin" /> : null}
          Capture
        </Button>
      </DialogFooter>
    </Dialog>
  )
}

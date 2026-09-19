import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import {
  api,
  type CreateProjectInput,
  type Project,
  type UpdateProjectInput,
} from '@/services/api'
import { StoreContext, type StoreValue } from '@/store-context'
import { reportError, toUserMessage } from '@/lib/errors'

/**
 * Write convention: pessimistic. Every write waits for the API to
 * confirm before `projects` state changes, so the store's state is
 * always what the backend actually has — never a locally-assumed change
 * that might not have saved. On failure, state is simply never touched,
 * a toast tells the user, and the rejection is re-thrown so the calling
 * component can revert any of its own local draft state (see
 * project-detail.tsx's `save()`, which is the one place with local
 * draft state that could otherwise go stale).
 */
export function StoreProvider({ children }: { children: ReactNode }) {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.listProjects()
      setProjects(data)
    } catch (err) {
      setError(
        toUserMessage(
          err,
          'Could not load your projects. Check your connection and try again.',
        ),
      )
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional fetch-on-mount: refresh() synchronously resets loading/error before its async api.listProjects() call, which can't happen during render.
    void refresh()
  }, [refresh])

  const createProject = useCallback(async (input: CreateProjectInput) => {
    try {
      const created = await api.createProject(input)
      setProjects((prev) => [created, ...prev])
      return created
    } catch (err) {
      reportError(err, "Couldn't create that project. Try again.")
      throw err
    }
  }, [])

  const updateProject = useCallback(
    async (id: string, patch: UpdateProjectInput) => {
      try {
        const updated = await api.updateProject(id, patch)
        setProjects((prev) => prev.map((p) => (p.id === id ? updated : p)))
        return updated
      } catch (err) {
        reportError(err, "Couldn't save that change. Try again.")
        throw err
      }
    },
    [],
  )

  const deleteProject = useCallback(async (id: string) => {
    try {
      await api.deleteProject(id)
      setProjects((prev) => prev.filter((p) => p.id !== id))
    } catch (err) {
      reportError(err, "Couldn't delete that project. Try again.")
      throw err
    }
  }, [])

  const addNote = useCallback(async (projectId: string, body: string) => {
    try {
      const { note, project } = await api.addNote(projectId, body)
      setProjects((prev) =>
        prev.map((p) => (p.id === project.id ? project : p)),
      )
      return note
    } catch (err) {
      reportError(err, "Couldn't add that note. Try again.")
      throw err
    }
  }, [])

  const deleteNote = useCallback(async (id: string) => {
    try {
      const project = await api.deleteNote(id)
      setProjects((prev) =>
        prev.map((p) => (p.id === project.id ? project : p)),
      )
    } catch (err) {
      reportError(err, "Couldn't delete that note. Try again.")
      throw err
    }
  }, [])

  const getProject = useCallback(
    (id: string) => projects.find((p) => p.id === id),
    [projects],
  )

  const value = useMemo<StoreValue>(
    () => ({
      projects,
      loading,
      error,
      refresh,
      getProject,
      createProject,
      updateProject,
      deleteProject,
      addNote,
      deleteNote,
    }),
    [
      projects,
      loading,
      error,
      refresh,
      getProject,
      createProject,
      updateProject,
      deleteProject,
      addNote,
      deleteNote,
    ],
  )

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>
}

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
      setError(err instanceof Error ? err.message : 'Failed to load projects')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional fetch-on-mount: refresh() synchronously resets loading/error before its async api.listProjects() call, which can't happen during render.
    void refresh()
  }, [refresh])

  const createProject = useCallback(async (input: CreateProjectInput) => {
    const created = await api.createProject(input)
    setProjects((prev) => [created, ...prev])
    return created
  }, [])

  const updateProject = useCallback(
    async (id: string, patch: UpdateProjectInput) => {
      const updated = await api.updateProject(id, patch)
      setProjects((prev) => prev.map((p) => (p.id === id ? updated : p)))
      return updated
    },
    [],
  )

  const deleteProject = useCallback(async (id: string) => {
    await api.deleteProject(id)
    setProjects((prev) => prev.filter((p) => p.id !== id))
  }, [])

  const addNote = useCallback(async (projectId: string, body: string) => {
    const { note, project } = await api.addNote(projectId, body)
    setProjects((prev) => prev.map((p) => (p.id === project.id ? project : p)))
    return note
  }, [])

  const deleteNote = useCallback(async (id: string) => {
    const project = await api.deleteNote(id)
    setProjects((prev) => prev.map((p) => (p.id === project.id ? project : p)))
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

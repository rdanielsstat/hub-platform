import {
  createContext,
  useCallback,
  useContext,
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

interface StoreValue {
  projects: Project[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  getProject: (id: string) => Project | undefined
  createProject: (input: CreateProjectInput) => Promise<Project>
  updateProject: (id: string, patch: UpdateProjectInput) => Promise<Project>
  deleteProject: (id: string) => Promise<void>
}

const StoreContext = createContext<StoreValue | null>(null)

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
    ],
  )

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>
}

export function useStore(): StoreValue {
  const ctx = useContext(StoreContext)
  if (!ctx) throw new Error('useStore must be used within a StoreProvider')
  return ctx
}

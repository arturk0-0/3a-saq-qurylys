import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '@/features/auth/AuthProvider'
import { errorMessage } from './labels'

export function useApiQuery<T>(path: string | null) {
  const { api } = useAuth()
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)
  const refresh = useCallback(() => setRevision((value) => value + 1), [])
  useEffect(() => {
    if (!path) { setData(null); setLoading(false); return }
    let active = true
    const controller = new AbortController()
    setLoading(true); setError(null); setData(null)
    api<T>(path, { signal: controller.signal })
      .then((result) => { if (active) setData(result) })
      .catch((error: unknown) => { if (active) setError(errorMessage(error)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false; controller.abort() }
  }, [api, path, revision])
  return { data, loading, error, refresh }
}

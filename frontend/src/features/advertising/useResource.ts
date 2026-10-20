import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuth } from '@/features/auth/AuthProvider'
import { errorMessage } from '@/lib/labels'

// Keep the current record mounted during refresh: a 409 must not erase its draft.
// A different path never exposes the previous record, even before the effect runs.
export function useResource<T>(path: string | null) {
  const { api } = useAuth()
  const [snapshot, setSnapshot] = useState<{ path: string | null; value: T | null }>({ path: null, value: null })
  const [status, setStatus] = useState<{ path: string | null; pending: boolean; error: string | null }>({ path: null, pending: false, error: null })
  const controller = useRef<AbortController | null>(null)
  const refresh = useCallback(async () => {
    controller.current?.abort()
    if (!path) return null
    const request = new AbortController()
    controller.current = request
    setStatus({ path, pending: true, error: null })
    try {
      const value = await api<T>(path, { signal: request.signal })
      if (request.signal.aborted) return null
      setSnapshot({ path, value }); setStatus({ path, pending: false, error: null })
      return value
    } catch (error) {
      if (request.signal.aborted) return null
      setStatus({ path, pending: false, error: errorMessage(error) })
      throw error
    }
  }, [api, path])
  useEffect(() => { void refresh().catch(() => {}); return () => controller.current?.abort() }, [refresh])
  const apply = useCallback((value: T) => { setSnapshot({ path, value }) }, [path])
  return { data: snapshot.path === path ? snapshot.value : null, loading: Boolean(path) && (status.path !== path || status.pending),
    error: status.path === path ? status.error : null, refresh, apply }
}

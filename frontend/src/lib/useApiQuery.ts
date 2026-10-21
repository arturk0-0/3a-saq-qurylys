import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuth } from '@/features/auth/AuthProvider'
import { errorMessage } from './labels'

export function useApiQuery<T>(path: string | null, { backgroundRefresh = false } = {}) {
  const { api } = useAuth()
  const [snapshot, setSnapshot] = useState<{ path: string; api: typeof api; value: T } | null>(null)
  const [status, setStatus] = useState<{ path: string | null; api: typeof api; pending: boolean; error: string | null } | null>(null)
  const request = useRef<{ path: string; api: typeof api; controller: AbortController } | null>(null)
  const [revision, setRevision] = useState(0)
  const refresh = useCallback(() => {
    // Polling must not cancel a slow request and restart it every interval.
    if (backgroundRefresh && request.current?.path === path && request.current.api === api) return
    setRevision((value) => value + 1)
  }, [api, path, backgroundRefresh])
  useEffect(() => {
    if (!path) { setSnapshot(null); setStatus(null); return }
    let active = true
    const controller = new AbortController()
    const current = { path, api, controller }
    request.current = current
    setStatus({ path, api, pending: true, error: null })
    if (!backgroundRefresh) setSnapshot(null)
    api<T>(path, { signal: controller.signal })
      .then((result) => { if (active) setSnapshot({ path, api, value: result }) })
      .catch((error: unknown) => { if (active) setStatus({ path, api, pending: false, error: errorMessage(error) }) })
      .finally(() => {
        if (request.current === current) request.current = null
        if (active) setStatus(previous => previous && { ...previous, pending: false })
      })
    return () => { active = false; controller.abort(); if (request.current === current) request.current = null }
  }, [api, path, revision, backgroundRefresh])
  const data = snapshot?.path === path && snapshot.api === api ? snapshot.value : null
  const currentStatus = status?.path === path && status.api === api ? status : null
  const pending = Boolean(path) && (!currentStatus || currentStatus.pending)
  return { data, loading: pending && (!backgroundRefresh || data === null),
    refreshing: pending && backgroundRefresh && data !== null, error: currentStatus?.error || null, refresh }
}

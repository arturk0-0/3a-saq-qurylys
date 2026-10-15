import { useState } from 'react'
import { useAuth } from '@/features/auth/AuthProvider'
import { ApiError } from './http'
import { errorMessage } from './labels'

// Keep the editor mounted while reading a newer version after a failed write.
// The caller shows the new server record and requires another explicit decision.
export function useReviewRecord<T extends { id: string; version: number }>(initial: T, path: string) {
  const { api } = useAuth()
  const [fresh, setFresh] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [conflict, setConflict] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const current = fresh?.id === initial.id && fresh.version >= initial.version ? fresh : initial
  function clearError() { setError(null); setConflict(false) }
  function failed(error: unknown) {
    setError(errorMessage(error))
    setConflict(error instanceof ApiError && error.status === 409)
  }
  async function refresh() {
    setRefreshing(true)
    try {
      setFresh(await api<T>(path))
      clearError()
    } catch (error) {
      // Keep the refresh action available if this read also fails.
      setError(errorMessage(error))
    } finally { setRefreshing(false) }
  }
  return { current, error, conflict, refreshing, clearError, failed, refresh }
}

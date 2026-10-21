import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { expect, it, vi } from 'vitest'
import { AuthContext } from '@/features/auth/AuthProvider'
import { useApiQuery } from './useApiQuery'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
function wrapper(api: unknown) {
  return ({ children }: { children: ReactNode }) => <AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api: api as never, signIn: vi.fn(), logout: vi.fn() }}>{children}</AuthContext.Provider>
}

it('keeps background data on refresh/error, skips overlapping requests, and recovers on retry', async () => {
  const first = deferred<string>(), second = deferred<string>(), third = deferred<string>()
  const api = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise).mockReturnValueOnce(third.promise)
  const { result } = renderHook(() => useApiQuery<string>('/materials', { backgroundRefresh: true }), { wrapper: wrapper(api) })
  act(() => { result.current.refresh(); result.current.refresh() })
  expect(api).toHaveBeenCalledTimes(1)
  await act(async () => first.resolve('saved'))
  expect(result.current.data).toBe('saved')
  act(() => result.current.refresh())
  expect(result.current).toMatchObject({ data: 'saved', loading: false, refreshing: true })
  act(() => result.current.refresh())
  expect(api).toHaveBeenCalledTimes(2)
  await act(async () => second.reject(new Error('offline')))
  expect(result.current).toMatchObject({ data: 'saved', loading: false, refreshing: false, error: 'offline' })
  act(() => result.current.refresh())
  await act(async () => third.resolve('fresh'))
  expect(result.current).toMatchObject({ data: 'fresh', loading: false, refreshing: false, error: null })
})

it('hides old filter data and ignores its late response, and clears data when disabled', async () => {
  const oldRefresh = deferred<string>(), next = deferred<string>()
  const api = vi.fn().mockResolvedValueOnce('old').mockReturnValueOnce(oldRefresh.promise).mockReturnValueOnce(next.promise)
  const { result, rerender } = renderHook(({ path }) => useApiQuery<string>(path, { backgroundRefresh: true }), { initialProps: { path: '/old' as string | null }, wrapper: wrapper(api) })
  await act(async () => {})
  act(() => result.current.refresh())
  const signal = api.mock.calls[1][1].signal as AbortSignal
  rerender({ path: '/new' })
  expect(signal.aborted).toBe(true)
  expect(result.current).toMatchObject({ data: null, loading: true, error: null })
  await act(async () => oldRefresh.resolve('late old data'))
  expect(result.current.data).toBeNull()
  expect(result.current.loading).toBe(true)
  await act(async () => next.resolve('new'))
  expect(result.current.data).toBe('new')
  rerender({ path: null })
  expect(result.current).toMatchObject({ data: null, loading: false, refreshing: false, error: null })
})

it('preserves blocking refresh for existing callers and aborts on unmount', async () => {
  const pending = deferred<string>()
  const api = vi.fn().mockResolvedValueOnce('old').mockReturnValue(pending.promise)
  const { result, unmount } = renderHook(() => useApiQuery<string>('/data'), { wrapper: wrapper(api) })
  await act(async () => {})
  act(() => result.current.refresh())
  expect(result.current).toMatchObject({ data: null, loading: true, refreshing: false })
  const signal = api.mock.calls[1][1].signal as AbortSignal
  unmount()
  expect(signal.aborted).toBe(true)
  await act(async () => pending.resolve('late'))
})

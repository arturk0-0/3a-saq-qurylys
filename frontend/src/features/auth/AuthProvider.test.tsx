import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { App } from '@/app/App'
import { AuthProvider } from './AuthProvider'

const auth = vi.hoisted(() => ({
  listener: null as null | ((user: unknown) => Promise<void>),
  currentUser: { getIdToken: vi.fn(async () => 'test-only-token') },
}))
vi.mock('@/lib/firebase', () => ({ firebaseAuth: auth, missingFirebaseConfig: [] }))
vi.mock('firebase/auth', () => ({
  browserSessionPersistence: {}, setPersistence: vi.fn(), signInWithEmailAndPassword: vi.fn(),
  signOut: vi.fn(async () => { await auth.listener?.(null) }),
  onIdTokenChanged: vi.fn((_auth, listener) => { auth.listener = listener; return vi.fn() }),
}))

beforeEach(() => { auth.currentUser.getIdToken.mockReset().mockResolvedValue('test-only-token') })

async function signedInApp() {
  const fetcher = vi.fn(async (path: string) => new Response(JSON.stringify(path.endsWith('/me')
    ? { uid: 'test-analyst', role: 'analyst', email: 'analyst@example.test' }
    : { items: [], nextCursor: null, total: 0 }), { headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', fetcher)
  render(<MemoryRouter initialEntries={['/complexes']}><AuthProvider><App /></AuthProvider></MemoryRouter>)
  await act(async () => { await auth.listener?.(auth.currentUser) })
  // Load the lazy workspace before exercising token rejection; keep auth assertions below.
  await screen.findByText('ЖК не найдены', {}, { timeout: 5_000 })
  return fetcher
}

it('hides the workspace when a previously accepted token is rejected by the API', async () => {
  const fetcher = await signedInApp()
  fetcher.mockImplementation(async () => new Response(JSON.stringify({ code: 'INVALID_TOKEN' }), { status: 401 }))
  fireEvent.click(screen.getByRole('link', { name: 'Реклама' }))
  await screen.findByRole('heading', { name: 'Доступ не подтверждён' })
  expect(screen.queryByRole('navigation', { name: 'Основная навигация' })).not.toBeInTheDocument()
  expect(screen.getByRole('alert')).toHaveTextContent('Сессия истекла')
  fireEvent.click(screen.getByRole('button', { name: 'Выйти' }))
  await screen.findByRole('button', { name: 'Войти' })
})

it('hides protected content if Firebase cannot refresh an expired token', async () => {
  const fetcher = await signedInApp()
  auth.currentUser.getIdToken.mockRejectedValue(Object.assign(new Error('private SDK detail'), { code: 'auth/user-token-expired' }))
  fireEvent.click(screen.getByRole('link', { name: 'Реклама' }))
  await screen.findByRole('heading', { name: 'Доступ не подтверждён' })
  expect(screen.queryByRole('navigation', { name: 'Основная навигация' })).not.toBeInTheDocument()
  expect(screen.getByRole('alert')).not.toHaveTextContent('private SDK detail')
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2))
})

it('keeps an authenticated workspace during an ordinary network outage', async () => {
  const fetcher = await signedInApp()
  fetcher.mockRejectedValue(new TypeError('offline'))
  fireEvent.click(screen.getByRole('link', { name: 'Реклама' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Нет связи с сервером')
  expect(screen.getByRole('navigation', { name: 'Основная навигация' })).toBeVisible()
})

it('does not expose SDK details or end the session for a temporary token refresh outage', async () => {
  await signedInApp()
  auth.currentUser.getIdToken.mockRejectedValue(Object.assign(new Error('private SDK detail'), { code: 'auth/network-request-failed' }))
  fireEvent.click(screen.getByRole('link', { name: 'Реклама' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось обновить доступ')
  expect(screen.getByRole('alert')).not.toHaveTextContent('private SDK detail')
  expect(screen.getByRole('navigation', { name: 'Основная навигация' })).toBeVisible()
})

it('ignores a late unauthorized response from a previous session after a new identity check', async () => {
  const fetcher = await signedInApp()
  let finishOldRequest!: (value: Response) => void
  fetcher.mockImplementationOnce(() => new Promise<Response>(resolve => { finishOldRequest = resolve }))
  fireEvent.click(screen.getByRole('link', { name: 'Реклама' }))
  await waitFor(() => expect(finishOldRequest).toBeDefined())
  await act(async () => { await auth.listener?.(null) })
  await screen.findByRole('button', { name: 'Войти' })
  await act(async () => { await auth.listener?.(auth.currentUser) })
  await screen.findByText('Материалов пока нет')
  await act(async () => { finishOldRequest(new Response('{"code":"INVALID_TOKEN"}', { status: 401 })) })
  expect(screen.getByRole('navigation', { name: 'Основная навигация' })).toBeVisible()
  expect(screen.queryByRole('heading', { name: 'Доступ не подтверждён' })).not.toBeInTheDocument()
})

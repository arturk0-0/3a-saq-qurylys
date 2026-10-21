import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { AuthContext } from '@/features/auth/AuthProvider'
import fixtures from '../../../qa/unified-advertising/fixtures.json'
import { AdvertisingPage } from './AdvertisingPage'

function deferred() {
  let resolve!: (value: unknown) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<unknown>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
const page = { items: [fixtures.material], nextCursor: null }
function setup(api: unknown) {
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
  return render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api: api as never, signIn: vi.fn(), logout: vi.fn() }}><MemoryRouter initialEntries={['/advertising']}><AdvertisingPage /></MemoryRouter></AuthContext.Provider>)
}
afterEach(() => vi.useRealTimers())

it('does not restart a slow initial request at the 30-second polling interval', async () => {
  vi.useFakeTimers()
  const pending = deferred()
  const api = vi.fn().mockReturnValue(pending.promise)
  setup(api)
  await act(async () => vi.advanceTimersByTime(65000))
  expect(api).toHaveBeenCalledTimes(1)
  expect(api.mock.calls[0][1].signal.aborted).toBe(false)
  await act(async () => pending.resolve(page))
  expect(screen.getByRole('heading', { name: fixtures.material.title })).toBeInTheDocument()
})

it('keeps the same cards and keyboard focus while polling, without overlapping refreshes', async () => {
  vi.useFakeTimers()
  const pending = deferred()
  const api = vi.fn().mockResolvedValueOnce(page).mockReturnValue(pending.promise)
  setup(api)
  await act(async () => {})
  const card = screen.getByRole('heading', { name: fixtures.material.title }).closest('article')
  const link = screen.getByRole('link', { name: /Проверить материал/ })
  link.focus()
  await act(async () => vi.advanceTimersByTime(30000))
  expect(screen.getByRole('heading', { name: fixtures.material.title }).closest('article')).toBe(card)
  expect(document.activeElement).toBe(link)
  expect(screen.queryByText(/Загружаем данные/)).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Обновить материалы' })).toBeDisabled()
  await act(async () => vi.advanceTimersByTime(60000))
  expect(api).toHaveBeenCalledTimes(2)
  expect(api.mock.calls[1][1].signal.aborted).toBe(false)
  await act(async () => pending.resolve({ items: [{ ...fixtures.material, title: 'Обновлённая карточка' }], nextCursor: null }))
  expect(screen.getByRole('heading', { name: 'Обновлённая карточка' }).closest('article')).toBe(card)
  expect(screen.getByRole('button', { name: 'Обновить материалы' })).not.toBeDisabled()
})

it('retains the last list after refresh failure but hides it when filters change', async () => {
  vi.useFakeTimers()
  const pending = deferred(), filtered = deferred()
  const api = vi.fn().mockResolvedValueOnce(page).mockReturnValueOnce(pending.promise).mockReturnValue(filtered.promise)
  setup(api)
  await act(async () => {})
  await act(async () => vi.advanceTimersByTime(30000))
  await act(async () => pending.reject(new Error('offline')))
  expect(screen.getByRole('alert')).toHaveTextContent('Показаны ранее загруженные материалы')
  expect(screen.getByRole('heading', { name: fixtures.material.title })).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Способ добавления'), { target: { value: 'manual' } })
  expect(screen.queryByRole('heading', { name: fixtures.material.title })).not.toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  await act(async () => filtered.resolve({ items: [], nextCursor: null }))
  expect(screen.getByText('Материалов пока нет')).toBeInTheDocument()
})

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { AuthContext } from '@/features/auth/AuthProvider'
import { ApiError, type ApiClient } from '@/lib/http'
import { CreateSignal, SignalDetail } from './SignalsPage'

it('requires a separate reason and sends the signal version for a return', async () => {
  const signal = { id: 's1', complexId: 'c1', title: 'Учебный сигнал', reason: 'Проверка',
    status: 'pending_review', version: 2, createdBy: 'author', createdAt: '2026-10-15T00:00:00Z',
    reviewNotes: '', reviewer: null, reviewedAt: null,
    snapshot: { complex: { id: 'c1', name: 'DEMO объект', version: 1 }, risk: { score: 35, zone: 'YELLOW', factors: [] }, evidence: [], capturedAt: '2026-10-15T00:00:00Z' } }
  const api = vi.fn(async (path: string, init?: RequestInit) => {
    if (path.endsWith('/history?limit=50')) return { items: [], nextCursor: null }
    if (path.includes('/complexes/')) return { version: 2 }
    if (init?.method === 'POST') { signal.status = 'returned'; signal.version = 3 }
    return { ...signal }
  })
  render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api: api as ApiClient, signIn: vi.fn(), logout: vi.fn() }}>
    <MemoryRouter initialEntries={['/signals/s1']}><Routes><Route path="/signals/:id" element={<SignalDetail />} /></Routes></MemoryRouter>
  </AuthContext.Provider>)
  expect(await screen.findByText(/Карточка ЖК изменена/)).toBeInTheDocument()
  expect(screen.getByRole('option', { name: 'Подтвердить сигнал' })).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Обоснование решения'), { target: { value: 'Нужно обновить снимок' } })
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить решение по сигналу' }))
  await waitFor(() => expect(screen.getByText('Возвращён')).toBeInTheDocument())
  const request = api.mock.calls.find(([, init]) => init?.method === 'POST')!
  expect(request[0]).toBe('/api/v1/signals/s1/decision')
  expect(JSON.parse(String(request[1]?.body))).toEqual({ action: 'return', expectedVersion: 2, notes: 'Нужно обновить снимок' })
})

function signalFixture() {
  return { id: 's1', complexId: 'c1', title: 'DEMO — сигнал', reason: 'Проверка',
    status: 'pending_review', version: 2, createdBy: 'author', createdAt: '2026-10-15T00:00:00Z',
    reviewNotes: '', reviewer: null, reviewedAt: null,
    snapshot: { complex: { id: 'c1', name: 'DEMO объект', version: 1 }, risk: { score: 35, zone: 'YELLOW', factors: [] }, evidence: [], capturedAt: '2026-10-15T00:00:00Z' } }
}

function renderSignal(api: ApiClient) {
  return render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api, signIn: vi.fn(), logout: vi.fn() }}><MemoryRouter initialEntries={['/signals/s1']}><Routes><Route path="/signals/:id" element={<SignalDetail />} /></Routes></MemoryRouter></AuthContext.Provider>)
}

it('preserves decision notes through a failed save and explicit data refresh', async () => {
  const signal = signalFixture()
  let writes = 0
  const api = vi.fn(async (path: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      if (++writes === 1) throw new ApiError(409, 'CONFLICT', 'Обновите данные')
      return { ...signal, status: 'returned' }
    }
    if (path.includes('/history')) return { items: [], nextCursor: null }
    if (path.includes('/complexes/')) return { version: 1 }
    return { ...signal }
  })
  renderSignal(api as ApiClient)
  fireEvent.change(await screen.findByLabelText('Обоснование решения'), { target: { value: 'Не потерять комментарий при обновлении' } })
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить решение по сигналу' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Обновите данные')
  fireEvent.click(screen.getByRole('button', { name: 'Обновить' }))
  await waitFor(() => expect(api.mock.calls.filter(([path]) => path === '/api/v1/signals/s1')).toHaveLength(2))
  expect(await screen.findByLabelText('Обоснование решения')).toHaveValue('Не потерять комментарий при обновлении')
  expect(writes).toBe(1)
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить решение по сигналу' }))
  await waitFor(() => expect(writes).toBe(2))
  const request = api.mock.calls.filter(([, init]) => init?.method === 'POST').at(-1)!
  expect(JSON.parse(String(request[1]?.body)).notes).toBe('Не потерять комментарий при обновлении')
})

it('blocks confirmation while current object data is unavailable and recovers independently', async () => {
  let objectReads = 0
  const api = vi.fn(async (path: string, _init?: RequestInit) => {
    if (path.includes('/history')) return { items: [], nextCursor: null }
    if (path.includes('/complexes/')) {
      if (++objectReads === 1) throw new Error('Нет связи с карточкой')
      return { version: 1 }
    }
    return signalFixture()
  })
  renderSignal(api as ApiClient)
  expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось проверить актуальность')
  expect(screen.getByRole('option', { name: 'Подтвердить сигнал' })).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Обоснование решения'), { target: { value: 'Текст сохранён' } })
  fireEvent.click(screen.getByRole('button', { name: 'Повторить' }))
  await waitFor(() => expect(screen.getByRole('option', { name: 'Подтвердить сигнал' })).not.toBeDisabled())
  expect(screen.getByLabelText('Обоснование решения')).toHaveValue('Текст сохранён')
  expect(api.mock.calls.every(([, init]) => !init || !(init as RequestInit).method)).toBe(true)
})

it('downloads the private PDF through a temporary attached link without losing notes', async () => {
  const makeUrl = vi.fn().mockReturnValue('blob:test-private-pdf')
  const revokeUrl = vi.fn()
  vi.stubGlobal('URL', class extends URL { static createObjectURL = makeUrl; static revokeObjectURL = revokeUrl })
  const schedule = vi.spyOn(globalThis, 'setTimeout')
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    expect(this.isConnected).toBe(true)
    expect(this.download).toBe('saq-signal-s1.pdf')
  })
  const api = vi.fn(async (path: string) => {
    if (path.endsWith('/report')) return new Blob(['%PDF-test-only'], { type: 'application/pdf' })
    if (path.includes('/history')) return { items: [], nextCursor: null }
    if (path.includes('/complexes/')) return { version: 1 }
    return signalFixture()
  })
  renderSignal(api as ApiClient)
  fireEvent.change(await screen.findByLabelText('Обоснование решения'), { target: { value: 'Текст решения' } })
  fireEvent.click(screen.getByRole('button', { name: 'Скачать PDF' }))
  await waitFor(() => expect(click).toHaveBeenCalledOnce())
  expect(makeUrl).toHaveBeenCalledOnce()
  expect(document.querySelector('a[download]')).toBeNull()
  expect(screen.getByLabelText('Обоснование решения')).toHaveValue('Текст решения')
  expect(screen.getByText('События истории пока не найдены.')).toBeInTheDocument()
  const cleanupIndex = schedule.mock.calls.findIndex(([, delay]) => delay === 10000)
  expect(cleanupIndex).toBeGreaterThanOrEqual(0)
  clearTimeout(schedule.mock.results[cleanupIndex].value as ReturnType<typeof setTimeout>)
  ;(schedule.mock.calls[cleanupIndex][0] as () => void)()
  expect(revokeUrl).toHaveBeenCalledWith('blob:test-private-pdf')
})

it('does not save an HTML error page as a PDF or discard the decision text', async () => {
  const makeUrl = vi.fn()
  vi.stubGlobal('URL', class extends URL { static createObjectURL = makeUrl })
  const api = vi.fn(async (path: string) => {
    if (path.endsWith('/report')) return new Blob(['<html>Wrong API origin</html>'], { type: 'text/html' })
    if (path.includes('/history')) return { items: [], nextCursor: null }
    if (path.includes('/complexes/')) return { version: 1 }
    return signalFixture()
  })
  renderSignal(api as ApiClient)
  fireEvent.change(await screen.findByLabelText('Обоснование решения'), { target: { value: 'Решение не потеряно' } })
  fireEvent.click(screen.getByRole('button', { name: 'Скачать PDF' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Сервер не вернул PDF')
  expect(screen.getByLabelText('Обоснование решения')).toHaveValue('Решение не потеряно')
  expect(makeUrl).not.toHaveBeenCalled()
  expect(document.querySelector('a[download]')).toBeNull()
})

it('refreshes a stale complex version before retrying signal creation without losing the draft', async () => {
  let version = 1
  let writes = 0
  const api = vi.fn(async (_path: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      writes++
      if (writes === 1) { version = 2; throw new ApiError(409, 'CONFLICT', 'Данные изменились. Обновите страницу и повторите действие.') }
      return { id: 'new-signal' }
    }
    return { id: 'c1', name: 'DEMO — Объект', version, risk: { score: 10, zone: 'GREEN' } }
  })
  render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api: api as ApiClient, signIn: vi.fn(), logout: vi.fn() }}>
    <MemoryRouter initialEntries={['/signals/new?complex=c1']}><Routes><Route path="/signals/new" element={<CreateSignal />} /><Route path="/signals/:id" element={<p>Сигнал создан</p>} /></Routes></MemoryRouter>
  </AuthContext.Provider>)
  fireEvent.change(await screen.findByLabelText('Заголовок сигнала'), { target: { value: 'Мой заголовок' } })
  fireEvent.change(screen.getByLabelText('Основание для проверки'), { target: { value: 'Текст проверки, введённый до конфликта' } })
  fireEvent.click(screen.getByRole('button', { name: 'Создать черновик' }))
  await screen.findByRole('alert')
  fireEvent.click(screen.getByRole('button', { name: 'Обновить данные ЖК' }))
  expect(await screen.findByLabelText('Заголовок сигнала')).toHaveValue('Мой заголовок')
  expect(screen.getByLabelText('Основание для проверки')).toHaveValue('Текст проверки, введённый до конфликта')
  expect(writes).toBe(1)
  fireEvent.click(screen.getByRole('button', { name: 'Создать черновик' }))
  await screen.findByText('Сигнал создан')
  expect(JSON.parse(String(api.mock.calls.filter(([, init]) => init?.method === 'POST').at(-1)![1]?.body)))
    .toMatchObject({ expectedComplexVersion: 2, title: 'Мой заголовок', reason: 'Текст проверки, введённый до конфликта' })
})

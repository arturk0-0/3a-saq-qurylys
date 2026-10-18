import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { AuthContext } from '@/features/auth/AuthProvider'
import { ApiError, type ApiClient } from '@/lib/http'
import { TracePanel } from './TracePanel'

const candidate = { id: 'snapshot1', snapshot: { leftId: 'a', rightId: 'b', leftVersion: 3, rightVersion: 5,
  matches: [{ kind: 'phone', normalized: '+70000000001', left: [{ quote: '+7 (000) 000-00-01' }], right: [{ quote: 'https://wa.me/70000000001' }] }], nameOnly: false },
  otherAdvertisement: { id: 'b', complexId: 'c', platform: 'DEMO', account: 'fictional-two', sourceUrl: 'https://demo.invalid/two' }, saved: null }
function setup(api: ApiClient) {
  render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api,
    signIn: vi.fn(), logout: vi.fn() }}><MemoryRouter><TracePanel adId="a" /></MemoryRouter></AuthContext.Provider>)
}
function result(saved: unknown = null) { return { items: [{ ...candidate, saved }], scannedCount: 12, scanLimited: false, resultsLimited: false, identifiersLimited: false } }

it('shows both original quotes and requires an explicit review without writing a factor', async () => {
  const api = vi.fn(async (path: string, init?: RequestInit) => {
    if (!init?.method) return result()
    if (path.endsWith('/decision')) return { id: 'snapshot1', status: 'confirmed', version: 2, reviewer: 'reviewer', reviewedAt: '2026-10-16T10:00:00Z', notes: 'Оригиналы сверены' }
    return { id: 'snapshot1', status: 'proposed', version: 1, reviewer: null, notes: '' }
  })
  setup(api as ApiClient)
  expect(await screen.findByText('+7 (000) 000-00-01')).toBeInTheDocument()
  expect(screen.getByText('https://wa.me/70000000001')).toBeInTheDocument()
  expect(api.mock.calls.filter(([, init]) => init?.method)).toHaveLength(0)
  expect(screen.getByRole('link', { name: 'К связанному объявлению →' })).toHaveAttribute('href', '/advertisements/b')
  fireEvent.click(screen.getByRole('button', { name: 'Рассмотреть совпадение' }))
  fireEvent.change(screen.getByLabelText('Обоснование совпадения'), { target: { value: 'Оригиналы сверены' } })
  fireEvent.submit(screen.getByLabelText('Обоснование совпадения').closest('form')!)
  expect(await screen.findByText('Совпадение подтверждено')).toBeInTheDocument()
  const writes = api.mock.calls.filter(([, init]) => init?.method === 'POST')
  expect(writes.map(([path]) => path)).toEqual(['/api/v1/advertisements/a/trace', '/api/v1/ad-links/snapshot1/decision'])
  expect(JSON.parse(String(writes[0][1]?.body))).toMatchObject({ expectedVersion: 3, expectedOtherVersion: 5, expectedSnapshotId: 'snapshot1', otherAdvertisementId: 'b' })
  expect(JSON.parse(String(writes[1][1]?.body))).toMatchObject({ decision: 'confirmed', notes: 'Оригиналы сверены', expectedVersion: 1 })
})

it('preserves the explanation and rejection after a concurrent review without replaying writes', async () => {
  let concurrent = false
  const api = vi.fn(async (path: string, init?: RequestInit) => {
    if (!init?.method) return result(concurrent ? { id: 'snapshot1', status: 'confirmed', version: 2, reviewer: 'other', notes: 'Другое решение' } : null)
    if (path.endsWith('/decision')) { concurrent = true; throw new ApiError(409, 'CONFLICT', 'Данные изменились') }
    return { id: 'snapshot1', status: 'proposed', version: 1 }
  })
  setup(api as ApiClient)
  fireEvent.click(await screen.findByRole('button', { name: 'Рассмотреть совпадение' }))
  fireEvent.change(screen.getByLabelText('Решение по совпадению'), { target: { value: 'rejected' } })
  fireEvent.change(screen.getByLabelText('Обоснование совпадения'), { target: { value: 'Моя заметка' } })
  fireEvent.submit(screen.getByLabelText('Обоснование совпадения').closest('form')!)
  await screen.findByRole('alert')
  expect(screen.getByLabelText('Обоснование совпадения')).toHaveValue('Моя заметка')
  expect(screen.getByLabelText('Решение по совпадению')).toHaveValue('rejected')
  fireEvent.click(screen.getByRole('button', { name: 'Обновить совпадения' }))
  await waitFor(() => expect(screen.getByText(/Несохранённое обоснование:/)).toHaveTextContent('Моя заметка'))
  expect(screen.queryByRole('button', { name: 'Сохранить решение о совпадении' })).not.toBeInTheDocument()
  expect(api.mock.calls.filter(([, init]) => init?.method)).toHaveLength(2)
})

it('shows bounded and empty results without implying absence of common ownership', async () => {
  const api = vi.fn().mockResolvedValue({ items: [], scannedCount: 199, scanLimited: true, resultsLimited: false, identifiersLimited: false })
  setup(api)
  expect(await screen.findByText('В проверенной выборке совпадений не найдено.')).toBeInTheDocument()
  expect(screen.getByText(/Показана ограниченная выборка/)).toBeInTheDocument()
  expect(screen.getByText(/Совпадение не доказывает общего владельца/)).toBeInTheDocument()
})

it('returns focus to the exact review trigger after cancelling a trace decision', async () => {
  const api = vi.fn().mockResolvedValue(result())
  setup(api)
  const trigger = await screen.findByRole('button', { name: 'Рассмотреть совпадение' })
  fireEvent.click(trigger)
  expect(screen.getByRole('heading', { name: 'Проверка совпадения' })).toHaveFocus()
  expect(trigger).toHaveAttribute('aria-expanded', 'true')
  fireEvent.click(screen.getByRole('button', { name: 'Отмена' }))
  expect(trigger).toHaveFocus()
  expect(trigger).toHaveAttribute('aria-expanded', 'false')
  expect(api).toHaveBeenCalledTimes(1)
})

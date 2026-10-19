import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { AuthContext } from '@/features/auth/AuthProvider'
import { ApiError, type ApiClient } from '@/lib/http'
import { RegistryPanel } from './RegistryPanel'
import { MonitoringPage } from './MonitoringPage'
import type { Finding, RegistryDocument } from './types'

const item = { id: 'synthetic-lead', version: 3, publishedAt: null, createdAt: '2026-10-19T10:00:00Z',
  aiStatus: 'not_requested', advertisementId: null } as Finding
const document: RegistryDocument = { provider: 'homeportal', recordId: '12', kind: 'regional_permit',
  name: 'Учебный берег', address: 'Риддер, учебный адрес', developer: 'Учебный застройщик',
  developerBin: '000000000001', holder: 'Учебный получатель', holderBin: '000000000002',
  reference: 'SYNTHETIC-1', issuedOn: '2020-01-01', sourceUrl: 'https://homeportal.kz/ru/projects/12',
  responseSha256: 'a'.repeat(64), documentSha256: 'b'.repeat(64), checkedAt: item.createdAt }
const results = { checkedAt: item.createdAt, sources: [
  { provider: 'homeportal', status: 'ok', candidates: [{ ...document, dataAsOf: null }], limited: false },
  { provider: 'ashyq', status: 'unavailable', candidates: [], limited: false },
] }
function setup(node: React.ReactNode, api: ApiClient) {
  return render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null,
    api, signIn: vi.fn(), logout: vi.fn() }}><MemoryRouter>{node}</MemoryRouter></AuthContext.Provider>)
}
async function selectDocument() {
  fireEvent.click(screen.getByText('Сверить разрешение или гарантию'))
  fireEvent.change(screen.getByLabelText('Название ЖК или адрес для сверки'), { target: { value: 'Учебный берег' } })
  fireEvent.click(screen.getByRole('button', { name: 'Найти в реестрах' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Проверить документ' }))
  await screen.findByLabelText('Проверенная дата рекламы')
}
it('only fetches on explicit actions and requires document, date, scope, validity and notes', async () => {
  const saved = vi.fn()
  const api = vi.fn(async (path: string, _init?: RequestInit) => path.includes('?q=') ? results : document)
  setup(<RegistryPanel item={item} disabled={false} saved={saved} />, api as ApiClient)
  expect(api).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: 'Основание проверено — завершить проверку' })).not.toBeInTheDocument()
  await selectDocument()
  expect(screen.getByText(/Источник недоступен или изменил формат/)).toBeInTheDocument()
  const button = screen.getByRole('button', { name: 'Основание проверено — завершить проверку' })
  expect(button).toBeDisabled()
  expect(screen.getByLabelText('Проверенная дата рекламы')).toHaveValue('')
  fireEvent.change(screen.getByLabelText('Проверенная дата рекламы'), { target: { value: '2026-10-18' } })
  fireEvent.change(screen.getByLabelText('Обоснование сверки документа'), { target: { value: 'SYNTHETIC QA: оригинал сверён' } })
  const checks = screen.getAllByRole('checkbox')
  checks.slice(0, -1).forEach(check => fireEvent.click(check))
  expect(button).toBeDisabled()
  fireEvent.click(checks.at(-1)!)
  fireEvent.click(button)
  await waitFor(() => expect(saved).toHaveBeenCalledTimes(1))
  const writes = api.mock.calls.filter(([, init]) => init?.method)
  expect(writes).toHaveLength(1)
  expect(writes[0][0]).toBe('/api/v1/monitoring/items/synthetic-lead/basis-review')
  expect(JSON.parse(String(writes[0][1]?.body))).toEqual({ expectedVersion: 3, recordId: '12',
    expectedDocumentSha256: 'b'.repeat(64), advertisementDate: '2026-10-18', objectMatches: true, phaseMatches: true, holderMatches: true,
    documentValidityChecked: true, advertisementDateChecked: true, otherRisksReviewed: true,
    notes: 'SYNTHETIC QA: оригинал сверён' })
})
it('keeps justification and checks after failed confirmation; blocks linked findings', async () => {
  const api = vi.fn(async (path: string, init?: RequestInit) => {
    if (init?.method) throw new ApiError(409, 'CONFLICT', 'Данные изменились')
    return path.includes('?q=') ? results : document
  })
  setup(<RegistryPanel item={item} disabled={false} saved={vi.fn()} />, api as ApiClient)
  await selectDocument()
  fireEvent.change(screen.getByLabelText('Проверенная дата рекламы'), { target: { value: '2026-10-18' } })
  fireEvent.change(screen.getByLabelText('Обоснование сверки документа'), { target: { value: 'Сверены документы' } })
  screen.getAllByRole('checkbox').forEach(check => fireEvent.click(check))
  fireEvent.click(screen.getByRole('button', { name: 'Основание проверено — завершить проверку' }))
  await screen.findByText('Данные изменились')
  expect(screen.getByLabelText('Обоснование сверки документа')).toHaveValue('Сверены документы')
  expect(screen.getAllByRole('checkbox').every(check => (check as HTMLInputElement).checked)).toBe(true)
})
it('uses original local publication date instead of campaign start and disallows attaching proof to linked ad', async () => {
  const api = vi.fn(async (path: string) => path.includes('?q=') ? results : document)
  setup(<RegistryPanel item={{ ...item, publishedAt: '2026-10-17T22:00:00Z', advertisementId: 'linked-ad' }} disabled={false} saved={vi.fn()} />, api as ApiClient)
  await selectDocument()
  expect(screen.getByLabelText('Проверенная дата рекламы')).toHaveValue('2026-10-18')
  expect(screen.getByLabelText('Проверенная дата рекламы')).toHaveAttribute('readonly')
  expect(screen.getByRole('button', { name: 'Основание проверено — завершить проверку' })).toBeDisabled()
})
it('shows an empty result as incomplete lookup, never as a confirmed R1', async () => {
  const api = vi.fn(async () => ({ ...results, sources: [{ provider: 'homeportal', status: 'ok', candidates: [], limited: false }] }))
  setup(<RegistryPanel item={item} disabled={false} saved={vi.fn()} />, api as ApiClient)
  fireEvent.click(screen.getByText('Сверить разрешение или гарантию'))
  fireEvent.change(screen.getByLabelText('Название ЖК или адрес для сверки'), { target: { value: 'Не найдено' } })
  fireEvent.click(screen.getByRole('button', { name: 'Найти в реестрах' }))
  expect(await screen.findByText(/Отсутствие совпадений не подтверждает отсутствие разрешения/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Основание проверено — завершить проверку' })).not.toBeInTheDocument()
})
it('defaults to server-filtered active queue and can explicitly retrieve all findings', async () => {
  const api = vi.fn(async (path: string) => path.endsWith('/status') ? {} : { items: [], nextCursor: null })
  setup(<MonitoringPage />, api as ApiClient)
  await screen.findByText('В этой очереди пока нет находок')
  expect(api.mock.calls.some(([path]) => path.includes('/items?limit=20&status=active'))).toBe(true)
  fireEvent.change(screen.getByLabelText('Статус находки'), { target: { value: 'all' } })
  await waitFor(() => expect(api.mock.calls.some(([path]) => path === '/api/v1/monitoring/items?limit=20')).toBe(true))
  expect(screen.getByLabelText('Статус находки')).toHaveValue('all')
})

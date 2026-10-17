import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { AuthContext } from '@/features/auth/AuthProvider'
import { ApiError, type ApiClient } from '@/lib/http'
import { MonitoringPage } from './MonitoringPage'
import { FindingDetail } from './FindingDetail'
import { SourceManager } from './SourceManager'
import type { Finding } from './types'

const item: Finding = {
  id: 'lead1', title: 'Synthetic QA lead', text: 'DEMO Өскемен, квартиры. Депозит. <img src=x onerror=alert(1)>',
  originalUrl: 'https://example.org/qa-ad', discoveryUrl: 'https://www.bing.com/search?q=qa',
  contentKind: 'search_snippet', account: 'example.org', publishedAt: null,
  createdAt: '2026-10-17T10:00:00Z', lastSeenAt: '2026-10-17T10:00:00Z',
  regionMatches: ['өскемен'], housingMatches: ['квартир'], paymentMatches: ['депозит'],
  textSha256: 'a'.repeat(64), responseSha256: 'b'.repeat(64), revisionKey: 'c'.repeat(64),
  sourceIds: ['s1'], status: 'new', notes: '', reviewer: null, reviewedAt: null,
  version: 1, aiStatus: 'not_requested', aiError: null, aiModel: null,
  extraction: null, advertisementId: null,
}
function setup(node: React.ReactNode, api: ApiClient, entries = ['/monitoring']) {
  return render(<AuthContext.Provider value={{ status: 'authenticated', profile: null,
    error: null, api, signIn: vi.fn(), logout: vi.fn() }}>
    <MemoryRouter initialEntries={entries}>{node}</MemoryRouter>
  </AuthContext.Provider>)
}
it('distinguishes Instagram target unavailability and search snippets without starting collection or AI', async () => {
  const api = vi.fn(async (path: string, _init?: RequestInit) => {
    if (path.endsWith('/status')) return { workerLastTickAt: null, dailyFetchUsed: 0,
      dailyFetchLimit: 100, maxAutoAiPerRun: 1, liveRegistryEnabled: false, instagramTargetedAds: 'not_connected' }
    if (path.endsWith('/sources')) return { items: [] }
    if (path.endsWith('/items/lead1')) return item
    if (path.includes('/history')) return { items: [], nextCursor: null }
    return { items: [item], nextCursor: null }
  })
  const result = setup(<MonitoringPage />, api as ApiClient)
  expect(await screen.findByText('Synthetic QA lead')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Автосбор таргетированной рекламы KZ пока не подключён' })).toBeInTheDocument()
  expect(screen.getByText('Фрагмент поиска')).toBeInTheDocument()
  expect(screen.getByText(/Ручной сбор доступен/)).toBeInTheDocument()
  expect(result.container.querySelector('img')).toBeNull()
  expect(api.mock.calls.every(([, init]) => !init?.method)).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Рассмотреть находку' }))
  expect(await screen.findByRole('heading', { name: 'Проверка находки' })).toBeInTheDocument()
})
it('source creation needs explicit opt-in for paid automatic AI', async () => {
  const api = vi.fn(async () => ({ id: 's1' }))
  setup(<SourceManager sources={[]} changed={vi.fn()} />, api as ApiClient)
  const checkbox = screen.getByRole('checkbox')
  expect(checkbox).not.toBeChecked()
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить источник' }))
  await screen.findByText(/Источник сохранён/)
  const first = JSON.parse(String((api.mock.calls as unknown as [string, RequestInit][])[0][1].body))
  expect(first).toMatchObject({ kind: 'web_search', autoAnalyze: false, intervalMinutes: 60 })
  fireEvent.click(checkbox)
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить источник' }))
  await waitFor(() => expect(api).toHaveBeenCalledTimes(2))
  const second = JSON.parse(String((api.mock.calls as unknown as [string, RequestInit][])[1][1].body))
  expect(second.autoAnalyze).toBe(true)
})
it('expert conflict keeps notes across refresh and retries with the new version without writing a factor', async () => {
  let current = { ...item }
  const api = vi.fn(async (path: string, init?: RequestInit) => {
    if (path.includes('/history')) return { items: [], nextCursor: null }
    if (!init?.method) return current
    if (path.endsWith('/review')) {
      const body = JSON.parse(String(init.body))
      if (body.expectedVersion === 1) {
        current = { ...current, version: 2 }
        throw new ApiError(409, 'CONFLICT', 'Данные изменились')
      }
      current = { ...current, version: 3, status: body.decision, notes: body.notes }
      return current
    }
    throw new Error('Unexpected mutation: ' + path)
  })
  setup(<FindingDetail id="lead1" liveRegistry={false} changed={vi.fn()} />, api as ApiClient)
  const notes = await screen.findByLabelText('Обоснование решения')
  fireEvent.change(notes, { target: { value: 'QA: сверить исходный пост' } })
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить решение эксперта' }))
  await screen.findByText('Данные изменились')
  fireEvent.click(screen.getByRole('button', { name: 'Обновить материал' }))
  expect(await screen.findByLabelText('Обоснование решения')).toHaveValue('QA: сверить исходный пост')
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить решение эксперта' }))
  await screen.findByText(/Решение по находке сохранено/)
  const writes = api.mock.calls.filter(([, init]) => init?.method)
  expect(writes).toHaveLength(2)
  expect(writes.every(([path]) => path.endsWith('/review'))).toBe(true)
  expect(JSON.parse(String(writes[1][1]?.body))).toMatchObject({ expectedVersion: 2, notes: 'QA: сверить исходный пост' })
})
it('does not offer attaching real findings to the DEMO registry or invent a publication date', async () => {
  const api = vi.fn(async (path: string) => path.includes('/history') ? { items: [], nextCursor: null } : item)
  setup(<FindingDetail id="lead1" liveRegistry={false} changed={vi.fn()} />, api as ApiClient)
  expect(await screen.findByText(/Реальную публикацию нельзя приписывать/)).toBeInTheDocument()
  expect(screen.getByText(/Опубликовано: Не указано/)).toBeInTheDocument()
  expect(screen.queryByLabelText('Реальный жилой комплекс')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Анализировать Gemini — платный запрос' })).toBeInTheDocument()
})


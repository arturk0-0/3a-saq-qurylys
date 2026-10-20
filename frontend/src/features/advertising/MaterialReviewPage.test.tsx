import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import fixtures from '../../../qa/unified-advertising/fixtures.json'
import { AuthContext } from '@/features/auth/AuthProvider'
import { ApiError } from '@/lib/http'
import type { Complex } from '@/lib/types'
import { MaterialReviewPage } from './MaterialReviewPage'
import { AdvertisingPage } from './AdvertisingPage'
import type { MaterialDetail, ReviewBody } from './types'

function setup(initial = fixtures.material as MaterialDetail, review?: (body: ReviewBody, count: number) => Promise<MaterialDetail>) {
  let detail = structuredClone(initial)
  let complex = structuredClone(fixtures.complex) as Complex
  const writes: ReviewBody[] = []
  const api = vi.fn(async (path: string, init?: RequestInit) => {
    if (path.endsWith('/review')) {
      const body = JSON.parse(String(init?.body)) as ReviewBody; writes.push(body)
      const saved = review ? await review(body, writes.length) : structuredClone(fixtures.saved) as MaterialDetail
      detail = saved; return saved
    }
    if (path.endsWith('/retry-analysis')) { detail = { ...detail, version: detail.version + 1, analysis: { ...detail.analysis, status: 'queued', canRetry: false } }; return detail }
    if (path.startsWith('/api/v1/materials/')) return structuredClone(detail)
    if (path.startsWith('/api/v1/complexes?')) return { items: [complex], nextCursor: null }
    if (path.startsWith('/api/v1/complexes/')) return structuredClone(complex)
    throw new Error('Unexpected test API path: ' + path)
  })
  render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api: api as never, signIn: vi.fn(), logout: vi.fn() }}><MemoryRouter initialEntries={[`/advertising/materials/${detail.id}?q=deposit`]}><Routes><Route path="/advertising/materials/:id" element={<MaterialReviewPage />} /></Routes></MemoryRouter></AuthContext.Provider>)
  return { api, writes, update(value: MaterialDetail, complexVersion = 5) { detail = structuredClone(value); complex = { ...complex, version: complexVersion } } }
}

async function choose() {
  await screen.findByLabelText('Решение по гипотезе 1 (R2)')
  await waitFor(() => expect(screen.getByLabelText('ЖК материала')).not.toBeDisabled())
  fireEvent.change(screen.getByLabelText('Решение по гипотезе 1 (R2)'), { target: { value: 'confirmed' } })
  fireEvent.change(screen.getByLabelText('Решение по гипотезе 2 (R3)'), { target: { value: 'insufficient' } })
  fireEvent.change(screen.getByLabelText('Общий комментарий'), { target: { value: 'QA — оригинал сверен' } })
}

it('sends one atomic review with versions and only selected decisions, keeping priority separate from returned risks', async () => {
  const state = setup()
  await choose()
  expect(screen.getByText('Приоритет проверки: Высокий · 82')).toBeInTheDocument()
  expect(screen.getByText('10 · Зелёная зона')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить проверку' }))
  await screen.findByText('35 · Жёлтая зона')
  expect(state.writes).toHaveLength(1)
  expect(state.writes[0]).toMatchObject({ expectedVersion: 1, revisionId: 'revision-1', complexId: 'demo-complex-04', expectedComplexVersion: 4,
    decisions: [{ hypothesisId: 'h2', decision: 'confirmed' }, { hypothesisId: 'h3', decision: 'insufficient' }], notes: 'QA — оригинал сверен', disposition: 'reviewed' })
  expect(state.writes[0].requestId).toMatch(/^[a-f0-9-]{36}$/)
  expect(state.api.mock.calls.some(([path]) => /\/factors\/|\/decision$|\/analyze$/.test(path))).toBe(false)
  expect(screen.queryByRole('button', { name: /Анализировать|Проанализировать/ })).not.toBeInTheDocument()
  expect(screen.getByRole('link', { name: '← Все материалы' })).toHaveAttribute('href', '/advertising?q=deposit')
})

it('reuses the same request ID and payload after a lost response without automatically retrying', async () => {
  const state = setup(undefined, async (_body, count) => {
    if (count === 1) throw new ApiError(0, 'NETWORK_ERROR', 'Нет связи с сервером')
    return structuredClone(fixtures.saved) as MaterialDetail
  })
  await choose(); fireEvent.click(screen.getByRole('button', { name: 'Сохранить проверку' }))
  await screen.findByRole('alert')
  expect(state.writes).toHaveLength(1)
  expect(screen.getByLabelText('Общий комментарий')).toHaveValue('QA — оригинал сверен')
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить проверку' }))
  await screen.findByText('35 · Жёлтая зона')
  expect(state.writes).toHaveLength(2); expect(state.writes[1]).toEqual(state.writes[0])
})

it('preserves notes/choices on 409, refreshes both records, requires acknowledgment, and retries only explicitly', async () => {
  const state = setup(undefined, async (_body, count) => {
    if (count === 1) throw new ApiError(409, 'CONFLICT', 'Данные изменились')
    return structuredClone(fixtures.saved) as MaterialDetail
  })
  await choose(); fireEvent.click(screen.getByRole('button', { name: 'Сохранить проверку' }))
  await screen.findByRole('alert')
  expect(screen.getByRole('button', { name: 'Сохранить проверку' })).toBeDisabled()
  state.update({ ...structuredClone(fixtures.material) as MaterialDetail, version: 2, revisionId: 'revision-2' })
  fireEvent.click(screen.getByRole('button', { name: 'Обновить материал и ЖК' }))
  const ack = await screen.findByRole('checkbox', { name: /Я сверил обновлённые данные/ })
  expect(screen.getByLabelText('Общий комментарий')).toHaveValue('QA — оригинал сверен')
  expect(screen.getByLabelText('Решение по гипотезе 1 (R2)')).toHaveValue('confirmed')
  expect(state.writes).toHaveLength(1)
  fireEvent.click(ack); expect(state.writes).toHaveLength(1)
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить проверку' }))
  await screen.findByText('35 · Жёлтая зона')
  expect(state.writes[1]).toMatchObject({ expectedVersion: 2, revisionId: 'revision-2', expectedComplexVersion: 5 })
  expect(state.writes[1].requestId).not.toBe(state.writes[0].requestId)
})

it('does not transfer previous confirmations when the complex is removed and does not show a signal link for an unsaved relation', async () => {
  const state = setup(fixtures.saved as MaterialDetail)
  await screen.findByLabelText('ЖК материала')
  await waitFor(() => expect(screen.getByLabelText('ЖК материала')).not.toBeDisabled())
  fireEvent.change(screen.getByLabelText('ЖК материала'), { target: { value: '' } })
  expect(screen.getByLabelText('Решение по гипотезе 1 (R2)')).toHaveValue('pending')
  expect(screen.queryByRole('link', { name: /Создать сигнал/ })).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Общий комментарий'), { target: { value: 'Связь требует проверки' } })
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить проверку' }))
  await waitFor(() => expect(state.writes).toHaveLength(1))
  expect(state.writes[0]).toMatchObject({ complexId: null, expectedComplexVersion: null, decisions: [] })
})

it('keeps a rejected server review as an editable draft and reports insufficient evidence without partial client risk changes', async () => {
  const state = setup(undefined, async () => { throw new ApiError(422, 'VALIDATION_ERROR', 'private provider details') })
  await choose(); fireEvent.click(screen.getByRole('button', { name: 'Сохранить проверку' }))
  const error = await screen.findByRole('alert')
  expect(error).toHaveTextContent('недостаточно доказательств')
  expect(error).not.toHaveTextContent('private provider details')
  expect(screen.getByText('10 · Зелёная зона')).toBeInTheDocument()
  expect(screen.getByLabelText('Общий комментарий')).toHaveValue('QA — оригинал сверен')
  expect(state.writes).toHaveLength(1)
})

it('offers analysis retry only after a retryable failure and queues it without a direct AI request', async () => {
  const state = setup(fixtures.failed as MaterialDetail)
  fireEvent.click(await screen.findByRole('button', { name: 'Повторить после ошибки анализа' }))
  await screen.findByText('Ожидает автоматического анализа')
  expect(screen.queryByRole('button', { name: 'Повторить после ошибки анализа' })).not.toBeInTheDocument()
  const calls = state.api.mock.calls.filter(([path]) => path.endsWith('/retry-analysis'))
  expect(calls).toHaveLength(1)
  expect(JSON.parse(String(calls[0][1]?.body))).toMatchObject({ expectedVersion: 1 })
})

it('labels pending/unsupported analysis honestly and never embeds external media or unsafe URLs', async () => {
  setup(fixtures.video as MaterialDetail)
  await screen.findByText('Автоанализ этого формата недоступен')
  expect(screen.getByText('Приоритет проверки: Ещё не оценено')).toBeInTheDocument()
  expect(screen.getByText('Подтверждённая оценка для материала пока недоступна. Это не нулевой риск.')).toBeInTheDocument()
  expect(screen.queryByRole('img')).not.toBeInTheDocument()
  expect(document.querySelector('video, iframe, a[href^="javascript:"]')).toBeNull()
  expect(screen.queryByRole('button', { name: 'Повторить после ошибки анализа' })).not.toBeInTheDocument()
})

it('keeps all materials server-paginated, resets cursors on filters and opens the chosen material with the list query', async () => {
  const api = vi.fn(async () => ({ items: [fixtures.material], nextCursor: 'opaque-page-2' }))
  render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api: api as never, signIn: vi.fn(), logout: vi.fn() }}><MemoryRouter initialEntries={['/advertising?review=reviewed']}><AdvertisingPage /></MemoryRouter></AuthContext.Provider>)
  await screen.findByRole('heading', { name: fixtures.material.title })
  expect(api).toHaveBeenLastCalledWith(expect.stringContaining('review=reviewed'), expect.anything())
  fireEvent.click(screen.getByRole('button', { name: 'Следующие материалы' }))
  await waitFor(() => expect(api).toHaveBeenLastCalledWith(expect.stringContaining('cursor=opaque-page-2'), expect.anything()))
  fireEvent.change(screen.getByLabelText('Способ добавления'), { target: { value: 'manual' } })
  await waitFor(() => expect(api).toHaveBeenLastCalledWith(expect.stringContaining('origin=manual'), expect.anything()))
  const last = api.mock.calls.at(-1) as unknown as [string]
  expect(new URL(last[0], 'https://test.invalid').searchParams.has('cursor')).toBe(false)
  const card = screen.getByRole('heading', { name: fixtures.material.title }).closest('article')!
  expect(within(card).getByRole('link', { name: /Проверить материал/ })).toHaveAttribute('href', expect.stringContaining('origin=manual'))
})

it('refreshes untouched notes and decisions from another reviewer without submitting them', async () => {
  const state = setup()
  await screen.findByLabelText('Общий комментарий')
  const fresh = structuredClone(fixtures.saved) as MaterialDetail
  fresh.review!.notes = 'Новая проверенная запись другого аналитика'
  state.update(fresh)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Обновить материал и ЖК' })).not.toBeDisabled())
  fireEvent.click(screen.getByRole('button', { name: 'Обновить материал и ЖК' }))
  await waitFor(() => expect(screen.getByLabelText('Общий комментарий')).toHaveValue(fresh.review!.notes))
  expect(screen.getByLabelText('Решение по гипотезе 1 (R2)')).toHaveValue('confirmed')
  expect(state.writes).toHaveLength(0)
})

it('recovers an invalidated server cursor by starting over with the same filters', async () => {
  const api = vi.fn(async (path: string) => {
    if (path.includes('cursor=')) throw new ApiError(409, 'CONFLICT', 'Выборка изменилась')
    return { items: [fixtures.material], nextCursor: null }
  })
  render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api: api as never, signIn: vi.fn(), logout: vi.fn() }}><MemoryRouter initialEntries={['/advertising?q=депозит&origin=manual&cursor=stale']}><AdvertisingPage /></MemoryRouter></AuthContext.Provider>)
  await screen.findByRole('alert')
  fireEvent.click(screen.getByRole('button', { name: 'Обновить список сначала' }))
  await screen.findByRole('heading', { name: fixtures.material.title })
  const params = new URL(api.mock.calls.at(-1)![0], 'https://test.invalid').searchParams
  expect(params.get('q')).toBe('депозит'); expect(params.get('origin')).toBe('manual')
  expect(params.has('cursor')).toBe(false)
})

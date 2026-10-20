import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import { AuthContext } from '@/features/auth/AuthProvider'
import { ApiError, type ApiClient } from '@/lib/http'
import { DronePage } from './DronePage'
import { DroneDetail } from './DroneDetail'
import type { Criterion, Inspection } from './types'

const criteria: Criterion[] = [
  { id: 'fence', label: 'Ограждение', sourceUrl: null },
  { id: 'signs', label: 'Знаки безопасности', sourceUrl: 'https://example.test/checklist' },
  { id: 'waste', label: 'Место отходов', sourceUrl: null },
]
const inspection: Inspection = { id: 'photo-one', title: 'Учебный облёт', complexId: null, complexName: null,
  capturedAt: null, version: 4, createdAt: '2026-10-20T08:00:00Z', checklist: criteria, status: 'analyzed',
  photo: { id: 'image-one', mediaType: 'image/png', sha256: 'a'.repeat(64), sizeBytes: 300, uploadedAt: '2026-10-20T08:01:00Z' },
  reviews: [], latestRunId: 'run-one', canAnalyze: true, analysisCount: 1, lastError: null,
  latestRun: { id: 'run-one', status: 'succeeded', createdAt: '2026-10-20T08:02:00Z', model: 'test-model',
    promptVersion: 'test-prompt', checklist: criteria, errorCode: null, result: {
      observations: [{ criterionId: 'fence', visibility: 'visible', explanation: 'Тестовое наблюдение ограждения.' },
        { criterionId: 'signs', visibility: 'not_visible', explanation: 'В этом ракурсе знаки не различимы.' },
        { criterionId: 'waste', visibility: 'uncertain', explanation: 'Нужен другой ракурс.' }],
      summary: 'Наблюдения для проверки.', limitations: 'Низкая детализация кадра.' } } }

beforeEach(() => {
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:drone-test') })
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
})
function setup(node: React.ReactNode, api: ApiClient, path = '/drone-inspections/photo-one') {
  return render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api,
    signIn: vi.fn(), logout: vi.fn() }}><MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/drone-inspections" element={node} /><Route path="/drone-inspections/:id" element={node} />
  </Routes></MemoryRouter></AuthContext.Provider>)
}
function reads(path: string) {
  if (path.endsWith('/photo')) return new Blob(['test image'], { type: 'image/png' })
  if (path.includes('/runs?')) return { items: [], nextCursor: null }
  return inspection
}

it('renders three distinct observations with limits and protected original; releases blob on unmount', async () => {
  const api = vi.fn(async (path: string) => reads(path))
  const view = setup(<DroneDetail />, api as ApiClient)
  expect(await screen.findByText('Видно на снимке', {}, { timeout: 5000 })).toBeInTheDocument()
  expect(screen.getByText('Не видно в кадре')).toBeInTheDocument()
  expect(screen.getByText('Нельзя определить')).toBeInTheDocument()
  expect(screen.getByText(/не означает, что объект отсутствует/)).toBeInTheDocument()
  expect(screen.getByText(/не изменяет рекламный риск/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Источник критерия ↗' })).toHaveAttribute('rel', 'noopener noreferrer')
  expect(await screen.findByAltText('Снимок: Учебный облёт')).toHaveAttribute('src', 'blob:drone-test')
  expect(api.mock.calls.every(([path]) => !path.endsWith('/analyze'))).toBe(true)
  view.unmount()
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:drone-test')
})
it('saves expert review separately and never prints reviewer UID', async () => {
  const api = vi.fn(async (path: string, init?: RequestInit) => {
    if (path.endsWith('/review') && init?.method) return { ...inspection, status: 'reviewed', version: 5,
      reviews: [{ runId: 'run-one', decision: 'needs_followup', notes: 'Проверить второй ракурс.', reviewer: 'private-reviewer-uid', reviewedAt: '2026-10-20T08:03:00Z' }] }
    return reads(path)
  })
  setup(<DroneDetail />, api as ApiClient)
  fireEvent.change(await screen.findByLabelText('Комментарий эксперта'), { target: { value: 'Проверить второй ракурс.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить решение' }))
  await screen.findByText('Рассмотрено экспертом')
  expect(screen.queryByText('private-reviewer-uid')).not.toBeInTheDocument()
  const write = api.mock.calls.find(([path]) => path.endsWith('/review'))
  expect(JSON.parse(String(write?.[1]?.body))).toEqual({ expectedVersion: 4, runId: 'run-one', decision: 'needs_followup', notes: 'Проверить второй ракурс.' })
})
it('retains expert notes on a version conflict and reconciles with read-only GET', async () => {
  const api = vi.fn(async (path: string, init?: RequestInit) => {
    if (init?.method) throw new ApiError(409, 'CONFLICT', 'Данные изменились')
    return reads(path)
  })
  setup(<DroneDetail />, api as ApiClient)
  fireEvent.change(await screen.findByLabelText('Комментарий эксперта'), { target: { value: 'Не потерять комментарий.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить решение' }))
  await screen.findByText('Данные изменились')
  expect(screen.getByLabelText('Комментарий эксперта')).toHaveValue('Не потерять комментарий.')
  expect(api.mock.calls.filter(([, init]) => init?.method)).toHaveLength(1)
})
it('does not retry AI after a timeout and preserves the original for a manual follow-up', async () => {
  const api = vi.fn(async (path: string, init?: RequestInit) => {
    if (path.endsWith('/analyze') && init?.method) throw new ApiError(503, 'AI_TIMEOUT', 'Ответ не получен')
    return reads(path)
  })
  setup(<DroneDetail />, api as ApiClient)
  fireEvent.click(await screen.findByRole('button', { name: 'Проанализировать заново' }))
  await screen.findByText('Ответ не получен')
  await waitFor(() => expect(screen.getByRole('button', { name: 'Проанализировать заново' })).toBeEnabled())
  expect(api.mock.calls.filter(([path, init]) => path.endsWith('/analyze') && init?.method)).toHaveLength(1)
  expect(screen.getByText('Наблюдения для проверки.')).toBeInTheDocument()
  expect(screen.getByAltText('Снимок: Учебный облёт')).toBeInTheDocument()
})
it('creates an unlinked inspection with edited checklist and uploads once without automatic analysis', async () => {
  const api = vi.fn(async (path: string, init?: RequestInit) => {
    if (path.endsWith('/checklist')) return { items: criteria }
    if (path.startsWith('/api/v1/complexes')) return { items: [] }
    if (init?.method) return { ...inspection, status: 'awaiting_photo', photo: null, version: 1, latestRunId: null, latestRun: null }
    return { items: [], nextCursor: null }
  })
  setup(<DronePage />, api as ApiClient, '/drone-inspections')
  fireEvent.change(await screen.findByLabelText('Название инспекции'), { target: { value: 'Новый ракурс' } })
  fireEvent.change(await screen.findByLabelText('Пункт 1'), { target: { value: 'Граница площадки в этом кадре' } })
  fireEvent.change(screen.getByLabelText('Фотография с дрона'), { target: { files: [new File(['test'], 'drone.png', { type: 'image/png' })] } })
  // jsdom FileList injection does not set the native required-file validity flag.
  fireEvent.submit(screen.getByRole('button', { name: 'Загрузить фотографию' }).closest('form')!)
  await waitFor(() => expect(api.mock.calls.filter(([, init]) => init?.method)).toHaveLength(2))
  const [createPath, createInit] = api.mock.calls.find(([path, init]) => path === '/api/v1/drone-inspections' && init?.method)!
  expect(createPath).toBe('/api/v1/drone-inspections')
  expect(JSON.parse(String(createInit?.body))).toMatchObject({ title: 'Новый ракурс', complexId: null, capturedAt: null, checklist: [expect.objectContaining({ label: 'Граница площадки в этом кадре' }), ...criteria.slice(1)] })
  expect(api.mock.calls.some(([path]) => path.endsWith('/analyze'))).toBe(false)
})
it('rejects an oversized file before creating any server record', async () => {
  const api = vi.fn(async (path: string) => path.endsWith('/checklist') ? { items: criteria } : { items: [], nextCursor: null })
  setup(<DronePage />, api as ApiClient, '/drone-inspections')
  fireEvent.change(await screen.findByLabelText('Название инспекции'), { target: { value: 'Снимок' } })
  await screen.findByLabelText('Пункт 1')
  fireEvent.change(screen.getByLabelText('Фотография с дрона'), { target: { files: [new File([new Uint8Array(6 * 1024 * 1024 + 1)], 'large.png', { type: 'image/png' })] } })
  // jsdom FileList injection does not set the native required-file validity flag.
  fireEvent.submit(screen.getByRole('button', { name: 'Загрузить фотографию' }).closest('form')!)
  await screen.findByText('Выберите JPEG, PNG или WebP до 6 МБ.')
  expect(api.mock.calls.some(([path]) => path === '/api/v1/drone-inspections')).toBe(false)
})

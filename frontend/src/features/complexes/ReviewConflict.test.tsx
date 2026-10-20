import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { AuthContext } from '@/features/auth/AuthProvider'
import { ApiError, type ApiClient } from '@/lib/http'
import type { Complex, Evidence } from '@/lib/types'
import { ComplexDetail } from './ComplexDetail'
import { EvidenceReviewForm } from './EvidencePanel'
import { RiskPanel } from './RiskPanel'
import type { ReactNode } from 'react'

const complex = { id: 'c1', name: 'DEMO — Объект', city: 'Риддер', version: 1,
  legalBasis: { type: 'unknown', status: 'unknown', reference: '', source: '', validUntil: null },
  factors: [], risk: { score: 10, zone: 'GREEN', factors: [{ code: 'R2', status: 'unknown', weight: 25, points: 0, evidenceIds: [] }] } } as unknown as Complex
const proof = { id: 'proof', complexId: 'c1', version: 1, type: 'advertisement', status: 'unknown', excerpt: 'Депозит 100 000 тенге' } as Evidence

function renderReview(node: ReactNode, api: ApiClient) {
  return render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api, signIn: vi.fn(), logout: vi.fn() }}><MemoryRouter initialEntries={['/complexes/c1?tab=documents']}>{node}</MemoryRouter></AuthContext.Provider>)
}

it('refreshes a conflicted source review without losing notes or verified checkboxes', async () => {
  let writes = 0
  let reads = 0
  const saved = vi.fn()
  const api = vi.fn(async (_path: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      if (++writes === 1) throw new ApiError(409, 'CONFLICT', 'Данные изменились')
      return {}
    }
    if (++reads === 1) throw new ApiError(503, 'TEST_UNAVAILABLE', 'Временный сбой чтения')
    return { ...proof, version: 2, status: 'rejected', reviewer: 'other-reviewer' }
  })
  renderReview(<EvidenceReviewForm item={proof} onSaved={saved} onCancel={vi.fn()} />, api as ApiClient)
  fireEvent.click(screen.getByLabelText('Источник содержит прямое предложение внести платёж'))
  fireEvent.change(screen.getByLabelText('Обоснование решения'), { target: { value: 'Сверено мной; текст не потерять' } })
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить проверку' }))
  await screen.findByRole('alert')
  fireEvent.click(screen.getByRole('button', { name: 'Обновить источник' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Временный сбой чтения')
  expect(screen.getByLabelText('Обоснование решения')).toHaveValue('Сверено мной; текст не потерять')
  expect(screen.getByRole('button', { name: 'Сохранить проверку' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Обновить источник' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Сохранить проверку' })).not.toBeDisabled())
  expect(screen.getByText(/Актуальная версия источника: 2/)).toHaveTextContent('Источник отклонён')
  expect(screen.getByLabelText('Обоснование решения')).toHaveValue('Сверено мной; текст не потерять')
  expect(screen.getByLabelText('Источник содержит прямое предложение внести платёж')).toBeChecked()
  expect(writes).toBe(1)
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить проверку' }))
  await waitFor(() => expect(saved).toHaveBeenCalledOnce())
  expect(JSON.parse(String(api.mock.calls.filter(([, init]) => init?.method === 'POST')[1][1]?.body)))
    .toMatchObject({ expectedVersion: 2, paymentOfferVerified: true, notes: 'Сверено мной; текст не потерять' })
})

it('refreshes a conflicted factor and its server risk without submitting or discarding the draft', async () => {
  let writes = 0
  const api = vi.fn(async (path: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      if (++writes === 1) throw new ApiError(409, 'CONFLICT', 'Данные изменились')
      return {}
    }
    if (path === '/api/v1/complexes/c1') return { ...complex, version: 2, risk: { ...complex.risk, score: 35, zone: 'YELLOW' } }
    return { items: [{ ...proof, status: 'confirmed' }], nextCursor: null }
  })
  renderReview(<RiskPanel complex_={complex} onChanged={vi.fn()} />, api as ApiClient)
  fireEvent.click(screen.getByRole('button', { name: 'Решение по фактору R2' }))
  fireEvent.click(await screen.findByLabelText('Депозит 100 000 тенге'))
  fireEvent.change(screen.getByLabelText('Решение'), { target: { value: 'confirmed' } })
  fireEvent.change(screen.getByLabelText('Обоснование'), { target: { value: 'Черновик решения по R2' } })
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить решение' }))
  await screen.findByRole('alert')
  fireEvent.click(screen.getByRole('button', { name: 'Обновить данные ЖК' }))
  await screen.findByText('35 · Жёлтая зона')
  expect(screen.getByLabelText('Обоснование')).toHaveValue('Черновик решения по R2')
  expect(await screen.findByLabelText('Депозит 100 000 тенге')).toBeChecked()
  expect(writes).toBe(1)
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить решение' }))
  await waitFor(() => expect(writes).toBe(2))
  expect(JSON.parse(String(api.mock.calls.filter(([, init]) => init?.method === 'POST')[1][1]?.body)).expectedVersion).toBe(2)
})

it('refreshes a conflicted legal-basis review and retains edited fields for explicit review', async () => {
  let reads = 0
  let writes = 0
  const api = vi.fn(async (path: string, init?: RequestInit) => {
    if (init?.method === 'PATCH') {
      if (++writes === 1) throw new ApiError(409, 'CONFLICT', 'Данные изменились')
      return {}
    }
    if (path === '/api/v1/complexes/c1') return { ...complex, version: ++reads }
    return { items: [], nextCursor: null }
  })
  renderReview(<Routes><Route path="/complexes/:id" element={<ComplexDetail />} /></Routes>, api as ApiClient)
  fireEvent.click(await screen.findByRole('button', { name: 'Пересмотреть' }))
  fireEvent.change(screen.getByLabelText('Реквизиты'), { target: { value: 'Мой документ №123' } })
  fireEvent.change(screen.getByLabelText('Источник проверки'), { target: { value: 'Мой исходный текст' } })
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить проверку' }))
  await screen.findByRole('alert')
  fireEvent.click(screen.getByRole('button', { name: 'Обновить данные ЖК' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Сохранить проверку' })).not.toBeDisabled())
  expect(screen.getByLabelText('Реквизиты')).toHaveValue('Мой документ №123')
  expect(screen.getByLabelText('Источник проверки')).toHaveValue('Мой исходный текст')
  expect(writes).toBe(1)
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить проверку' }))
  await waitFor(() => expect(writes).toBe(2))
  expect(JSON.parse(String(api.mock.calls.filter(([, init]) => init?.method === 'PATCH')[1][1]?.body)).expectedVersion).toBe(2)
})

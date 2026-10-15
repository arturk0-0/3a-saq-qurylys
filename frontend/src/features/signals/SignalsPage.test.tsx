import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { AuthContext } from '@/features/auth/AuthProvider'
import type { ApiClient } from '@/lib/http'
import { SignalDetail } from './SignalsPage'

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

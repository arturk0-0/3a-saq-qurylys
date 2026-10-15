import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { AuthContext } from '@/features/auth/AuthProvider'
import type { ApiClient } from '@/lib/http'
import { ComplexDetail } from './ComplexDetail'

it('opens a specific evidence link even when it is absent from the first page', async () => {
  const complex = { id: 'c1', city: 'Риддер', name: 'DEMO — Объект', address: 'DEMO', demo: true,
    factors: [{ code: 'R2', status: 'confirmed', evidenceIds: ['e2'] }],
    risk: { score: 25, zone: 'YELLOW', factors: [{ code: 'R2', status: 'confirmed', evidenceIds: ['e2'], points: 25, weight: 25 }] } }
  const api = vi.fn(async (path: string) => {
    if (path === '/api/v1/complexes/c1') return complex
    if (path === '/api/v1/evidence/e2') return { id: 'e2', complexId: 'c1', type: 'advertisement', status: 'confirmed',
      excerpt: 'Точная цитата из выбранного источника', sourceUrl: 'https://demo.invalid/ad', capturedAt: '2026-10-15T00:00:00Z' }
    return { items: [], nextCursor: null }
  })
  render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api: api as ApiClient, signIn: vi.fn(), logout: vi.fn() }}>
    <MemoryRouter initialEntries={['/complexes/c1?tab=ads']}><Routes><Route path="/complexes/:id" element={<ComplexDetail />} /></Routes></MemoryRouter>
  </AuthContext.Provider>)
  fireEvent.click(await screen.findByRole('link', { name: 'Источник 1' }))
  expect(await screen.findByText('Точная цитата из выбранного источника')).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: 'Доказательства' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByText('Источник, выбранный по ссылке')).toBeInTheDocument()
  expect(screen.getByText('Источник, выбранный по ссылке')).toHaveFocus()
})

it('navigates tabs by keyboard with one tab stop and a labelled panel', async () => {
  const complex = { id: 'c1', city: 'Риддер', name: 'DEMO — Объект', address: 'DEMO', demo: true,
    developer: { name: 'DEMO', bin: '000000000001' }, stage: 'under_construction',
    progress: { claimedPercent: 50, verifiedPercent: null }, factors: [],
    risk: { score: 0, zone: 'GREEN', factors: [] } }
  const api = vi.fn(async (path: string) => path === '/api/v1/complexes/c1' ? complex : { items: [], nextCursor: null })
  render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api: api as ApiClient, signIn: vi.fn(), logout: vi.fn() }}>
    <MemoryRouter initialEntries={['/complexes/c1']}><Routes><Route path="/complexes/:id" element={<ComplexDetail />} /></Routes></MemoryRouter>
  </AuthContext.Provider>)
  const overview = await screen.findByRole('tab', { name: 'Обзор' })
  overview.focus()
  fireEvent.keyDown(overview, { key: 'ArrowRight' })
  const ads = screen.getByRole('tab', { name: 'Объявления' })
  expect(ads).toHaveFocus()
  expect(ads).toHaveAttribute('aria-selected', 'true')
  expect(overview).toHaveAttribute('tabindex', '-1')
  expect(screen.getByRole('tabpanel', { name: 'Объявления' })).toBeInTheDocument()
  fireEvent.keyDown(ads, { key: 'End' })
  expect(screen.getByRole('tab', { name: 'История' })).toHaveFocus()
  fireEvent.keyDown(screen.getByRole('tab', { name: 'История' }), { key: 'ArrowRight' })
  expect(overview).toHaveFocus()
  fireEvent.keyDown(overview, { key: 'ArrowLeft' })
  expect(screen.getByRole('tab', { name: 'История' })).toHaveFocus()
  fireEvent.keyDown(screen.getByRole('tab', { name: 'История' }), { key: 'Home' })
  expect(overview).toHaveAttribute('tabindex', '0')
  expect(overview).toHaveFocus()
})

it('distinguishes reviewed evidence from its original unverified AI provenance', async () => {
  const complex = { id: 'c1', city: 'Риддер', name: 'DEMO — Объект', address: 'DEMO', demo: true,
    factors: [], risk: { score: 10, zone: 'GREEN', factors: [] } }
  const api = vi.fn(async (path: string, _init?: RequestInit) => path === '/api/v1/complexes/c1' ? complex : {
    items: [{ id: 'e1', complexId: 'c1', type: 'advertisement', status: 'confirmed',
      excerpt: 'Проверенная цитата', sourceReference: 'AI hypothesis; advertising-extraction-v1; unverified', capturedAt: '2026-10-15T00:00:00Z' }], nextCursor: null,
  })
  render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api: api as ApiClient, signIn: vi.fn(), logout: vi.fn() }}><MemoryRouter initialEntries={['/complexes/c1?tab=evidence']}><Routes><Route path="/complexes/:id" element={<ComplexDetail />} /></Routes></MemoryRouter></AuthContext.Provider>)
  expect(await screen.findByText('Источник проверен')).toBeVisible()
  expect(screen.getByText(/В реквизитах указан AI-анализ/)).toBeVisible()
  const original = screen.getByText('AI hypothesis; advertising-extraction-v1; unverified')
  expect(original).not.toBeVisible()
  fireEvent.click(screen.getByText('Происхождение и версия анализа'))
  expect(original).toBeVisible()
  expect(screen.getByRole('button', { name: 'Пересмотреть проверку источника' })).toBeVisible()
  expect(api.mock.calls.every(([, init]) => !init || !(init as RequestInit).method)).toBe(true)
})

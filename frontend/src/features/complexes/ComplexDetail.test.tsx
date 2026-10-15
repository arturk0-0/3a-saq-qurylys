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
})

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { AuthContext } from '@/features/auth/AuthProvider'
import type { ApiClient } from '@/lib/http'
import { MatchingCandidates } from './MatchingCandidates'

function setup(api: ApiClient) {
  render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null,
    api, signIn: vi.fn(), logout: vi.fn() }}><MemoryRouter><MatchingCandidates adId="a1" runId="run1" /></MemoryRouter></AuthContext.Provider>)
}

it('requires a human comparison for ambiguous names and never writes a linkage or risk decision', async () => {
  const api = vi.fn().mockResolvedValue({ currentComplexId: 'c1', catalogLimited: false, groups: [
    { mention: 'Учебный квартал', ambiguous: true, candidateCount: 2, candidatesLimited: false,
      candidates: [{ complexId: 'c1', name: 'DEMO — Первый', city: 'Риддер', matchedBy: 'alias', matchedName: 'Учебный квартал', demo: true },
        { complexId: 'c2', name: 'DEMO — Второй', city: 'Алтай', matchedBy: 'name', matchedName: 'Учебный квартал', demo: true }] },
  ] })
  setup(api)
  expect(api).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Найти ЖК по названиям' }))
  expect(await screen.findByText(/Неоднозначно: найдено 2 ЖК/)).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Открыть выбранный ЖК →' })).not.toBeInTheDocument()
  const compare = screen.getByRole('button', { name: 'Сравнить: DEMO — Второй' })
  expect(compare).toHaveAttribute('aria-pressed', 'false')
  fireEvent.click(compare)
  expect(compare).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByRole('link', { name: 'Открыть выбранный ЖК →' })).toHaveAttribute('href', '/complexes/c2')
  expect(screen.getByText(/Кандидат отличается от текущей привязки/)).toBeInTheDocument()
  expect(api).toHaveBeenCalledOnce()
  expect(api).toHaveBeenCalledWith('/api/v1/advertisements/a1/matching-candidates?run_id=run1', expect.objectContaining({ signal: expect.anything() }))
})

it('retries lookup failures and never presents no match as missing legal permission', async () => {
  const api = vi.fn().mockRejectedValueOnce(new Error('Реестр недоступен')).mockResolvedValueOnce({ currentComplexId: 'c1', catalogLimited: true,
    groups: [{ mention: 'Неизвестное название', candidates: [], ambiguous: false, candidateCount: 0, candidatesLimited: false }] })
  setup(api)
  fireEvent.click(screen.getByRole('button', { name: 'Найти ЖК по названиям' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Реестр недоступен')
  fireEvent.click(screen.getByRole('button', { name: 'Повторить' }))
  await waitFor(() => expect(screen.getByText(/Это не означает отсутствие правового основания и не даёт R1/)).toBeInTheDocument())
  expect(screen.getByText(/Поиск ограничен первыми 500/)).toBeInTheDocument()
})

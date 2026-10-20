import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { AuthContext } from '@/features/auth/AuthProvider'
import type { Complex } from '@/lib/types'
import { RiskPanel } from './RiskPanel'

const complex = { id: 'c1', version: 4, factors: [], risk: { score: 10, zone: 'GREEN', factors: [
  { code: 'R2', status: 'unknown', points: 0, weight: 25, evidenceIds: [] },
  { code: 'R3', status: 'confirmed', points: 10, weight: 10, evidenceIds: ['r3-proof'] },
] } } as unknown as Complex

it('focuses factor review and preserves notes and selected proof across a failed save', async () => {
  let attempts = 0
  const api = vi.fn(async (_path: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      if (++attempts === 1) throw new Error('Временная ошибка сохранения')
      return {}
    }
    return { items: [{ id: 'proof', status: 'confirmed', excerpt: 'Прямое предложение внести депозит' }], nextCursor: null }
  })
  const changed = vi.fn()
  render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api: api as never, signIn: vi.fn(), logout: vi.fn() }}><MemoryRouter><RiskPanel complex_={complex} onChanged={changed} /></MemoryRouter></AuthContext.Provider>)
  fireEvent.click(screen.getByRole('button', { name: 'Решение по фактору R2' }))
  expect(screen.getByRole('heading', { name: 'Решение по R2' })).toHaveFocus()
  const proof = await screen.findByLabelText('Прямое предложение внести депозит')
  fireEvent.click(proof)
  fireEvent.change(screen.getByLabelText('Решение'), { target: { value: 'confirmed' } })
  fireEvent.change(screen.getByLabelText('Обоснование'), { target: { value: 'Оригинал и цитата сверены' } })
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить решение' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Временная ошибка сохранения')
  expect(screen.getByLabelText('Обоснование')).toHaveValue('Оригинал и цитата сверены')
  expect(proof).toBeChecked()
  expect(screen.getByText('10 · Зелёная зона')).toBeInTheDocument()
  expect(changed).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить решение' }))
  await waitFor(() => expect(changed).toHaveBeenCalledOnce())
  const writes = api.mock.calls.filter(([, init]) => init?.method === 'POST')
  expect(writes).toHaveLength(2)
  expect(JSON.parse(String(writes[1][1]?.body))).toEqual({ code: 'R2', decision: 'confirmed', evidenceIds: ['proof'], notes: 'Оригинал и цитата сверены', expectedVersion: 4 })
  // The frontend does not add 25 locally: it waits for the refreshed server result.
  expect(screen.getByText('10 · Зелёная зона')).toBeInTheDocument()
})

it('returns keyboard focus to the factor trigger after cancelling review', () => {
  const api = vi.fn().mockResolvedValue({ items: [], nextCursor: null })
  render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api, signIn: vi.fn(), logout: vi.fn() }}><MemoryRouter><RiskPanel complex_={complex} onChanged={vi.fn()} /></MemoryRouter></AuthContext.Provider>)
  const trigger = screen.getByRole('button', { name: 'Решение по фактору R2' })
  fireEvent.click(trigger)
  fireEvent.click(screen.getByRole('button', { name: 'Отмена' }))
  expect(trigger).toHaveFocus()
  expect(trigger).toHaveAttribute('aria-expanded', 'false')
})

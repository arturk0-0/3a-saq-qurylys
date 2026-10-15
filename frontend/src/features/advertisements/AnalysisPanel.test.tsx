import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { AuthContext } from '@/features/auth/AuthProvider'
import { AnalysisPanel } from './AnalysisPanel'

it('requests analysis and reviews a hypothesis without confirming a factor', async () => {
  let analyzed = false
  let accepted = false
  const api = vi.fn(async (path: string, init?: RequestInit) => {
    if (path.endsWith('/analyze')) { analyzed = true; return {} }
    if (path.endsWith('/decision')) { accepted = true; return {} }
    if (path.includes('/hypotheses')) return { items: analyzed ? [{ id: 'h1', code: 'R2', quote: 'Депозит 100 000 тенге', explanation: 'Платёж', confidence: null, status: accepted ? 'accepted' : 'proposed', evidenceId: 'e1', model: 'test-model', version: 1 }] : [], nextCursor: null }
    if (path.includes('/analysis')) return { items: [], nextCursor: null }
    expect(init?.method).toBeUndefined()
    return { id: 'a1', complexId: 'c1', version: 3, attachmentIds: [] }
  })
  render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api: api as never, signIn: vi.fn(), logout: vi.fn() }}><MemoryRouter><AnalysisPanel adId="a1" /></MemoryRouter></AuthContext.Provider>)
  fireEvent.click(await screen.findByRole('button', { name: 'Анализировать выбранный источник' }))
  expect(await screen.findByText('Депозит 100 000 тенге')).toBeInTheDocument()
  const request = api.mock.calls.find(([path]) => path.endsWith('/analyze'))!
  expect(JSON.parse(String(request[1]?.body))).toMatchObject({ expectedVersion: 3, screenshotId: null })
  fireEvent.click(screen.getByRole('button', { name: 'Рассмотреть гипотезу' }))
  fireEvent.change(screen.getByLabelText('Обоснование'), { target: { value: 'Цитата требует проверки источника' } })
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить решение' }))
  await waitFor(() => expect(screen.getByText(/Балл пока не изменён/)).toBeInTheDocument())
  expect(api.mock.calls.some(([path]) => path.includes('/factors/'))).toBe(false)
  expect(api.mock.calls.some(([path]) => path.includes('/evidence/') && path.endsWith('/decision'))).toBe(false)
})

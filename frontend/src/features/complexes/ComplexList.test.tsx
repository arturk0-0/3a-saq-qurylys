import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { AuthContext } from '@/features/auth/AuthProvider'
import { ComplexList } from './ComplexList'

function Detail() {
  const navigate = useNavigate()
  return <button onClick={() => navigate(-1)}>Назад в результаты</button>
}

it('restores the exact registry search and filters after opening a card and going back', async () => {
  const api = vi.fn(async (_path: string, _init?: RequestInit) => ({ items: [{ id: 'c1', name: 'DEMO — Объект', city: 'Риддер', stage: 'under_construction',
    progress: { verifiedPercent: null, claimedPercent: 30 }, risk: { score: 35, zone: 'YELLOW' } }], nextCursor: null }))
  render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api: api as never, signIn: vi.fn(), logout: vi.fn() }}>
    <MemoryRouter initialEntries={['/complexes']}><Routes><Route path="/complexes" element={<ComplexList />} /><Route path="/complexes/:id" element={<Detail />} /></Routes></MemoryRouter>
  </AuthContext.Provider>)
  await screen.findByText('Объект')
  fireEvent.change(screen.getByLabelText('Город'), { target: { value: 'Риддер' } })
  fireEvent.change(screen.getByLabelText('Приоритет'), { target: { value: 'YELLOW' } })
  fireEvent.change(screen.getByLabelText('Поиск ЖК'), { target: { value: 'Объект' } })
  fireEvent.click(screen.getByRole('button', { name: 'Найти' }))
  await waitFor(() => expect(api).toHaveBeenLastCalledWith(expect.stringContaining('q='), expect.anything()))
  fireEvent.click(await screen.findByRole('link', { name: 'Карточка' }))
  fireEvent.click(screen.getByRole('button', { name: 'Назад в результаты' }))
  await screen.findByText('Объект')
  expect(screen.getByLabelText('Поиск ЖК')).toHaveValue('Объект')
  expect(screen.getByLabelText('Город')).toHaveValue('Риддер')
  expect(screen.getByLabelText('Приоритет')).toHaveValue('YELLOW')
  const params = new URL(api.mock.calls.at(-1)![0], 'https://test.invalid').searchParams
  expect(Object.fromEntries(params)).toMatchObject({ q: 'Объект', city: 'Риддер', zone: 'YELLOW' })
})

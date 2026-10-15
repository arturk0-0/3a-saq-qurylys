import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { AuthContext, type Profile } from '@/features/auth/AuthProvider'

const profile: Profile = { uid: 'analyst', role: 'analyst', email: 'analyst@example.test', displayName: null }
const row = { id: 'demo-a', name: 'DEMO — Проверочный ЖК', address: 'Вымышленный адрес', city: 'Риддер', stage: 'under_construction',
  progress: { verifiedPercent: null, claimedPercent: 50 }, risk: { score: 35, zone: 'YELLOW' }, scenario: 'A' }
function renderApp(api: ReturnType<typeof vi.fn>) {
  return render(<AuthContext.Provider value={{ status: 'authenticated', profile, error: null,
    api, signIn: vi.fn(), logout: vi.fn() }}><MemoryRouter><App /></MemoryRouter></AuthContext.Provider>)
}

describe('analyst workspace', () => {
  it('renders server risk and submits filters to the protected API', async () => {
    const api = vi.fn().mockResolvedValue({ items: [row], total: 1, nextCursor: null })
    renderApp(api)
    expect(await screen.findByText('Проверочный ЖК')).toBeInTheDocument()
    expect(screen.getByText('35 · Требует проверки')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Карточка' })).toHaveAttribute('href', '/complexes/demo-a')
    fireEvent.change(screen.getByRole('combobox', { name: 'Приоритет' }), { target: { value: 'RED' } })
    await waitFor(() => expect(api).toHaveBeenLastCalledWith(expect.stringContaining('zone=RED'), expect.any(Object)))
    fireEvent.change(screen.getByRole('textbox', { name: 'Поиск ЖК' }), { target: { value: 'Риддер' } })
    fireEvent.click(screen.getByRole('button', { name: 'Найти' }))
    await waitFor(() => expect(new URL(api.mock.calls.at(-1)![0], 'https://test.invalid').searchParams.get('q')).toBe('Риддер'))
  })

  it('recovers from a failed query without displaying fabricated records', async () => {
    const api = vi.fn().mockRejectedValueOnce(new Error('Сеть недоступна')).mockResolvedValueOnce({ items: [row], total: 1, nextCursor: null })
    renderApp(api)
    expect(await screen.findByRole('alert')).toHaveTextContent('Сеть недоступна')
    expect(screen.queryByText('Проверочный ЖК')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Повторить' }))
    expect(await screen.findByText('Проверочный ЖК')).toBeInTheDocument()
  })

  it('shows an empty registry and navigates to advertisements', async () => {
    const api = vi.fn().mockResolvedValue({ items: [], total: 0, nextCursor: null })
    renderApp(api)
    expect(await screen.findByText('ЖК не найдены')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: 'Объявления' }))
    expect(await screen.findByText('Объявлений пока нет')).toBeInTheDocument()
    expect(api).toHaveBeenLastCalledWith('/api/v1/advertisements?limit=50', expect.any(Object))
  })
})

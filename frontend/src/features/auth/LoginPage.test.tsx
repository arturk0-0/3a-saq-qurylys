import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { App } from '@/app/App'
import { AuthContext } from './AuthProvider'

describe('access boundary', () => {
  it('does not render business navigation for an anonymous user', async () => {
    const signIn = vi.fn().mockRejectedValue(new Error('Неверные данные'))
    render(<MemoryRouter><AuthContext.Provider value={{ status: 'signed_out', profile: null,
      error: null, api: vi.fn(), signIn, logout: vi.fn() }}><App /></AuthContext.Provider></MemoryRouter>)
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Электронная почта'), { target: { value: 'a@example.test' } })
    fireEvent.change(screen.getByLabelText('Пароль'), { target: { value: 'test-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Войти' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Неверные данные')
    expect(signIn).toHaveBeenCalledWith('a@example.test', 'test-password')
    await waitFor(() => expect(screen.getByLabelText('Пароль')).toHaveValue(''))
  })

  it('shows setup instructions when Firebase is not configured', () => {
    render(<MemoryRouter><AuthContext.Provider value={{ status: 'unavailable', profile: null,
      error: null, api: vi.fn(), signIn: vi.fn(), logout: vi.fn() }}><App /></AuthContext.Provider></MemoryRouter>)
    expect(screen.getByRole('heading', { name: 'Подключите рабочую среду' })).toBeInTheDocument()
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
  })
})

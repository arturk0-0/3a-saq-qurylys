import { fireEvent, render, screen } from '@testing-library/react'
import { StrictMode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { App } from './App'

describe('application skeleton', () => {
  it('shows successful API health and navigates to an unimplemented module', async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ok', service: 'saq-qurylys-api' }) })
    vi.stubGlobal('fetch', fetch)
    render(<StrictMode><MemoryRouter><App /></MemoryRouter></StrictMode>)
    expect(await screen.findByText('API доступен')).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith('/api/v1/health', expect.objectContaining({ signal: expect.any(AbortSignal) }))
    fireEvent.click(screen.getByRole('link', { name: 'Реестр ЖК' }))
    expect(screen.getByRole('heading', { name: 'Реестр ЖК' })).toBeInTheDocument()
    expect(screen.getByText(/Раздел ещё не реализован/)).toBeInTheDocument()
  })

  it('shows connection failures and allows retry', async () => {
    const fetch = vi.fn().mockResolvedValueOnce({ ok: false }).mockResolvedValueOnce({ ok: true, json: async () => ({ status: 'ok', service: 'saq-qurylys-api' }) })
    vi.stubGlobal('fetch', fetch)
    render(<MemoryRouter><App /></MemoryRouter>)
    expect(await screen.findByText(/API недоступен/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Проверить снова' }))
    expect(await screen.findByText('API доступен')).toBeInTheDocument()
  })

  it('rejects unexpected health responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ok' }) }))
    render(<MemoryRouter><App /></MemoryRouter>)
    expect(await screen.findByText('API вернул неожиданный ответ.')).toBeInTheDocument()
  })
})

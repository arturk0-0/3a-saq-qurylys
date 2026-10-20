import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { AuthContext } from '@/features/auth/AuthProvider'
import { SourcesSchedule } from './SourcesSchedule'

it('preserves source form and action feedback while refreshing sources after create and collection', async () => {
  const source = { id: 's', name: 'Мой источник', kind: 'web_search', target: 'ВКО квартиры', intervalMinutes: 90,
    autoAnalyze: false, enabled: true, version: 1, lastRunAt: null, nextRunAt: null, leaseUntil: null, lastError: null }
  let created = false
  const api = vi.fn(async (path: string, init?: RequestInit) => {
    if (path.endsWith('/run')) return { fetched: 3, relevant: 2, created: 1, duplicates: 1 }
    if (path.endsWith('/sources')) { if (init?.method === 'POST') created = true; return { items: created ? [source] : [] } }
    return { workerLastTickAt: null, dailyFetchUsed: 0, dailyFetchLimit: 100, instagramTargetedAds: 'not_connected' }
  })
  render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api: api as never, signIn: vi.fn(), logout: vi.fn() }}><MemoryRouter><SourcesSchedule /></MemoryRouter></AuthContext.Provider>)
  fireEvent.change(screen.getByLabelText('Название источника'), { target: { value: 'Мой источник' } })
  expect(screen.queryByRole('checkbox', { name: /Анализировать новые находки/ })).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Интервал сбора, минуты'), { target: { value: '90' } })
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить источник' }))
  await screen.findByRole('heading', { name: 'Мой источник' })
  expect(screen.getByText('Источник сохранён. Настройки применены.')).toBeInTheDocument()
  expect(screen.getByLabelText('Название источника')).toHaveValue('Мой источник')
  expect(screen.getByLabelText('Интервал сбора, минуты')).toHaveValue(90)
  fireEvent.click(screen.getByRole('button', { name: 'Получить публикации' }))
  await waitFor(() => expect(screen.getByText(/Сбор завершён: прочитано 3/)).toBeInTheDocument())
  expect(screen.getByLabelText('Название источника')).toHaveValue('Мой источник')
  expect(api.mock.calls.filter(([path]) => path.endsWith('/run'))).toHaveLength(1)
})

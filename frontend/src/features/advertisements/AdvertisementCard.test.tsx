import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { AuthContext } from '@/features/auth/AuthProvider'
import type { Advertisement } from '@/lib/types'
import { AdvertisementCard } from './AdvertisementsPage'

const ad = { id: 'a', complexId: 'c', platform: 'DEMO', account: 'fictional', sourceUrl: 'https://demo.invalid/a',
  text: 'DEMO: депозит', attachmentIds: ['image1'], version: 1 } as Advertisement

function setup() {
  const api = vi.fn(async (path: string) => {
    if (path.endsWith('/trace')) return { scannedCount: 1, items: [{ id: 'pair', saved: null,
      snapshot: { leftId: 'a', rightId: 'b', leftVersion: 1, rightVersion: 1, matches: [], nameOnly: true },
      otherAdvertisement: { id: 'b', complexId: 'c', platform: 'DEMO', account: 'another', sourceUrl: null } }] }
    if (path.includes('/hypotheses')) return { items: [{ id: 'h', code: 'R2', quote: 'депозит', explanation: 'TEST',
      confidence: null, status: 'proposed', evidenceId: 'e', model: 'TEST', version: 1 }] }
    if (path.includes('/analysis')) return { items: [] }
    return ad
  })
  render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api: api as never, signIn: vi.fn(), logout: vi.fn() }}><MemoryRouter><AdvertisementCard ad={ad} /></MemoryRouter></AuthContext.Provider>)
  expect(api).not.toHaveBeenCalled()
  return api
}

it('retains the selected screenshot and hypothesis draft through collapsing and reopening analysis', async () => {
  const api = setup()
  fireEvent.click(screen.getByRole('button', { name: 'Скриншоты и AI-анализ' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Рассмотреть гипотезу' }))
  fireEvent.change(screen.getByLabelText('Сохранённый материал'), { target: { value: 'image1' } })
  fireEvent.change(screen.getByLabelText('Решение по гипотезе'), { target: { value: 'rejected' } })
  fireEvent.change(screen.getByLabelText('Обоснование'), { target: { value: 'Моя несохранённая заметка' } })
  const reads = api.mock.calls.length
  fireEvent.click(screen.getByRole('button', { name: 'Скрыть анализ' }))
  expect(screen.queryByRole('region', { name: 'Анализ объявления' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Скриншоты и AI-анализ' }))
  expect(await screen.findByLabelText('Обоснование')).toHaveValue('Моя несохранённая заметка')
  expect(screen.getByLabelText('Решение по гипотезе')).toHaveValue('rejected')
  expect(screen.getByLabelText('Сохранённый материал')).toHaveValue('image1')
  expect(api).toHaveBeenCalledTimes(reads)
})

it('retains the advertising-trace explanation and rejection through hiding the panel', async () => {
  const api = setup()
  fireEvent.click(screen.getByRole('button', { name: 'Рекламный след' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Рассмотреть совпадение' }))
  fireEvent.change(screen.getByLabelText('Решение по совпадению'), { target: { value: 'rejected' } })
  fireEvent.change(screen.getByLabelText('Обоснование совпадения'), { target: { value: 'Сравниваю источники' } })
  const reads = api.mock.calls.length
  fireEvent.click(screen.getByRole('button', { name: 'Скрыть рекламный след' }))
  fireEvent.click(screen.getByRole('button', { name: 'Рекламный след' }))
  expect(await screen.findByLabelText('Обоснование совпадения')).toHaveValue('Сравниваю источники')
  expect(screen.getByLabelText('Решение по совпадению')).toHaveValue('rejected')
  expect(api).toHaveBeenCalledTimes(reads)
})

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { AuthContext } from '@/features/auth/AuthProvider'
import type { ApiClient } from '@/lib/http'
import { AdvertisementForm } from './AdvertisementsPage'

it('recovers the complex selector without losing original ad text or auto-selecting a match', async () => {
  const api = vi.fn().mockRejectedValueOnce(new Error('Реестр недоступен'))
    .mockResolvedValueOnce({ items: [{ id: 'c1', name: 'DEMO — Первый' }, { id: 'c2', name: 'DEMO — Второй' }], nextCursor: null })
    .mockResolvedValueOnce({ id: 'a1' })
  const onSaved = vi.fn()
  render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null,
    api: api as ApiClient, signIn: vi.fn(), logout: vi.fn() }}><AdvertisementForm onSaved={onSaved} onCancel={vi.fn()} /></AuthContext.Provider>)
  const original = '  DEMO: внесите депозит.\nОригинальные пробелы сохранены.  '
  fireEvent.change(screen.getByLabelText('Текст объявления'), { target: { value: original } })
  expect(await screen.findByRole('alert')).toHaveTextContent('Реестр недоступен')
  expect(screen.getByRole('button', { name: 'Сохранить объявление' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Повторить' }))
  await screen.findByRole('option', { name: 'DEMO — Второй' })
  expect(screen.getByRole('combobox', { name: 'Жилой комплекс' })).toHaveValue('')
  expect(screen.getByLabelText('Текст объявления')).toHaveValue(original)
  fireEvent.change(screen.getByRole('combobox', { name: 'Жилой комплекс' }), { target: { value: 'c2' } })
  fireEvent.change(screen.getByLabelText('Площадка'), { target: { value: 'DEMO' } })
  fireEvent.change(screen.getByLabelText('Аккаунт / автор'), { target: { value: 'fictional' } })
  fireEvent.change(screen.getByLabelText('Оригинальная ссылка'), { target: { value: 'https://demo.invalid/new' } })
  fireEvent.change(screen.getByLabelText(/Дата публикации/), { target: { value: '2026-10-15T09:00' } })
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить объявление' }))
  await waitFor(() => expect(onSaved).toHaveBeenCalledOnce())
  expect(JSON.parse(api.mock.calls[2][1].body)).toMatchObject({ complexId: 'c2', text: original })
})

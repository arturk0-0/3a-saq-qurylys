import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { AuthContext } from '@/features/auth/AuthProvider'
import type { ApiClient } from '@/lib/http'
import { localDateTime } from '@/lib/labels'
import type { Evidence } from '@/lib/types'
import { EvidenceReviewForm } from './EvidencePanel'

const base = { id: 'e1', type: 'progress_report', status: 'unknown', version: 3,
  claimedPercent: null, verifiedPercent: null, claimedAt: null, verifiedAt: null,
  claimedSource: '', verifiedSource: '' } as Evidence

function setup(item: Evidence, api: ApiClient) {
  const onSaved = vi.fn()
  const view = render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null,
    api, signIn: vi.fn(), logout: vi.fn() }}><EvidenceReviewForm item={item} onSaved={onSaved} onCancel={vi.fn()} /></AuthContext.Provider>)
  return { ...view, onSaved }
}

it('allows rejecting an incomplete progress source without inventing percentages or dates', async () => {
  const api = vi.fn().mockResolvedValue({})
  const { container, onSaved } = setup(base, api)
  fireEvent.change(screen.getByLabelText('Обоснование решения'), { target: { value: 'Нет дат и подтверждённых измерений' } })
  expect(container.querySelector('form')!.checkValidity()).toBe(false)
  fireEvent.change(screen.getByRole('combobox', { name: 'Результат проверки' }), { target: { value: 'rejected' } })
  expect(container.querySelector('form')!.checkValidity()).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить проверку' }))
  await waitFor(() => expect(onSaved).toHaveBeenCalledOnce())
  expect(JSON.parse(api.mock.calls[0][1].body)).toMatchObject({ decision: 'rejected', expectedVersion: 3,
    claimedPercent: null, verifiedPercent: null, claimedAt: null, verifiedAt: null })
})

it('preserves existing dated measurements and typed notes across a failed save', async () => {
  const api = vi.fn().mockRejectedValueOnce(new Error('Сервис недоступен')).mockResolvedValueOnce({})
  const item = { ...base, claimedPercent: 70, verifiedPercent: 40, claimedAt: '2026-10-13T08:00:00Z',
    verifiedAt: '2026-10-14T09:00:00Z', claimedSource: 'Заявление', verifiedSource: 'Акт осмотра' }
  const { onSaved } = setup(item, api)
  expect(screen.getByLabelText('Дата заявления')).toHaveValue(localDateTime(item.claimedAt))
  expect(screen.getByLabelText('Дата проверки')).toHaveValue(localDateTime(item.verifiedAt))
  fireEvent.change(screen.getByLabelText('Обоснование решения'), { target: { value: 'Даты и акт сверены' } })
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить проверку' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Сервис недоступен')
  expect(screen.getByLabelText('Обоснование решения')).toHaveValue('Даты и акт сверены')
  expect(onSaved).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить проверку' }))
  await waitFor(() => expect(onSaved).toHaveBeenCalledOnce())
  expect(JSON.parse(api.mock.calls[1][1].body)).toMatchObject({ decision: 'confirmed',
    claimedAt: '2026-10-13T08:00:00.000Z', verifiedAt: '2026-10-14T09:00:00.000Z',
    claimedPercent: 70, verifiedPercent: 40, notes: 'Даты и акт сверены', expectedVersion: 3 })
})

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import fixtures from '../../../qa/unified-advertising/fixtures.json'
import { AuthContext } from '@/features/auth/AuthProvider'
import { Originals } from './Originals'
import { ScreenshotUpload } from './ScreenshotUpload'
import type { MaterialDetail } from './types'
import { ApiError } from '@/lib/http'

it('keeps originals on a paginated failure and explicitly retries the same page without losing the selected publication', async () => {
  let attempts = 0
  const api = vi.fn(async (_path: string, _init?: RequestInit) => { if (++attempts === 1) throw new Error('История временно недоступна'); return { items: [fixtures.lastOccurrence], nextCursor: null } })
  const received = vi.fn()
  render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api: api as never, signIn: vi.fn(), logout: vi.fn() }}><Originals detail={fixtures.material as MaterialDetail} requestedId={null} onRecords={received} /></AuthContext.Provider>)
  fireEvent.change(screen.getByLabelText('Публикация'), { target: { value: 'o2' } })
  fireEvent.click(screen.getByRole('button', { name: 'Следующие публикации' }))
  await screen.findByRole('alert')
  expect(screen.getByLabelText('Публикация')).toHaveValue('o2')
  expect(screen.getByText(fixtures.material.text)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Повторить' }))
  await waitFor(() => expect(screen.getAllByRole('option')).toHaveLength(3))
  expect(api.mock.calls[0][0]).toBe(api.mock.calls[1][0])
  expect(api.mock.calls[1][0]).toContain('cursor=occ-page-2')
  expect(screen.getByLabelText('Публикация')).toHaveValue('o2')
})

it('loads private images through the authorized file client and releases their blob URLs, never embedding a supplied token URL', async () => {
  const create = vi.fn(() => 'blob:test-private')
  const revoke = vi.fn()
  vi.stubGlobal('URL', class extends URL { static createObjectURL = create; static revokeObjectURL = revoke })
  const detail = structuredClone(fixtures.material) as MaterialDetail
  detail.occurrences[0].media = [{ id: 'private-file', kind: 'image', url: 'https://fixture.invalid/private?token=TEST-ONLY', availability: 'private', analyzed: true }]
  const api = vi.fn(async () => new Blob(['image'], { type: 'image/png' }))
  const view = render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api: api as never, signIn: vi.fn(), logout: vi.fn() }}><Originals detail={detail} requestedId={null} onRecords={vi.fn()} /></AuthContext.Provider>)
  expect(view.container.innerHTML).not.toContain('token=')
  expect(api).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Открыть скриншот' }))
  expect(await screen.findByRole('img')).toHaveAttribute('src', 'blob:test-private')
  expect(api).toHaveBeenCalledWith('/api/v1/evidence/private-file/file')
  view.unmount(); expect(revoke).toHaveBeenCalledWith('blob:test-private')
})

it('rejects an invalid upload locally and preserves a valid file through a stale advertisement version and retry', async () => {
  let version = 1
  let posts = 0
  const api = vi.fn(async (_path: string, init?: RequestInit) => {
    if (init?.method === 'POST') { if (++posts === 1) { version = 2; throw new ApiError(409, 'CONFLICT', 'Данные изменились') }; return { id: 'file' } }
    return { id: 'ad', version, attachmentIds: [] }
  })
  const changed = vi.fn(async () => {})
  render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api: api as never, signIn: vi.fn(), logout: vi.fn() }}><ScreenshotUpload adId="ad" disabled={false} changed={changed} onBusy={vi.fn()} /></AuthContext.Provider>)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Загрузить скриншот' })).not.toBeDisabled())
  const input = screen.getByLabelText('Добавить скриншот к материалу')
  fireEvent.change(input, { target: { files: [new File(['bad'], 'bad.pdf', { type: 'application/pdf' })] } })
  fireEvent.submit(input.closest('form')!)
  expect(await screen.findByRole('alert')).toHaveTextContent('JPEG, PNG или WebP')
  expect(posts).toBe(0)
  const file = new File(['png'], 'original.png', { type: 'image/png' })
  fireEvent.change(input, { target: { files: [file] } }); fireEvent.submit(input.closest('form')!)
  await screen.findByRole('button', { name: 'Обновить версию объявления' })
  expect((input as HTMLInputElement).files?.[0]).toBe(file)
  fireEvent.click(screen.getByRole('button', { name: 'Обновить версию объявления' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Загрузить скриншот' })).not.toBeDisabled())
  fireEvent.submit(input.closest('form')!)
  await screen.findByText(/Скриншот «original.png» сохранён/)
  expect(changed).toHaveBeenCalledTimes(1)
  const writes = api.mock.calls.filter(([, init]) => init?.method === 'POST')
  expect(writes[1][0]).toContain('expected_version=2')
  expect(writes[1][1]?.body).toBe(file)
  expect(api.mock.calls.some(([path]) => path.endsWith('/analyze'))).toBe(false)
})

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { AuthContext } from '@/features/auth/AuthProvider'
import { EvidenceFile } from './EvidenceFile'

function setup(api: ReturnType<typeof vi.fn>) {
  return render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api: api as never, signIn: vi.fn(), logout: vi.fn() }}><EvidenceFile id="image1" /></AuthContext.Provider>)
}

it('rejects a successful HTML response instead of presenting it as the original screenshot', async () => {
  const makeUrl = vi.fn().mockReturnValue('blob:html')
  vi.stubGlobal('URL', class extends URL { static createObjectURL = makeUrl; static revokeObjectURL = vi.fn() })
  setup(vi.fn().mockResolvedValue(new Blob(['<html>Gateway error</html>'], { type: 'text/html' })))
  fireEvent.click(screen.getByRole('button', { name: 'Открыть скриншот' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Сервер не вернул изображение')
  expect(makeUrl).not.toHaveBeenCalled()
  expect(screen.queryByRole('link', { name: 'Скачать оригинал' })).not.toBeInTheDocument()
})

it('allows retry after image decoding fails and releases the unusable Blob URL', async () => {
  const makeUrl = vi.fn().mockReturnValueOnce('blob:broken').mockReturnValueOnce('blob:valid')
  const revoke = vi.fn()
  vi.stubGlobal('URL', class extends URL { static createObjectURL = makeUrl; static revokeObjectURL = revoke })
  const api = vi.fn().mockResolvedValue(new Blob(['TEST image bytes'], { type: 'image/png' }))
  const view = setup(api)
  fireEvent.click(screen.getByRole('button', { name: 'Открыть скриншот' }))
  const image = await screen.findByRole('img')
  fireEvent.error(image)
  expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось отобразить скриншот')
  await waitFor(() => expect(revoke).toHaveBeenCalledWith('blob:broken'))
  fireEvent.click(screen.getByRole('button', { name: 'Открыть скриншот' }))
  expect(await screen.findByRole('img')).toHaveAttribute('src', 'blob:valid')
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  view.unmount()
  expect(revoke).toHaveBeenCalledWith('blob:valid')
  expect(api).toHaveBeenCalledTimes(2)
})

it('does not create a Blob URL for a file request that finishes after leaving the page', async () => {
  const makeUrl = vi.fn()
  vi.stubGlobal('URL', class extends URL { static createObjectURL = makeUrl })
  let finish!: (blob: Blob) => void
  const api = vi.fn(() => new Promise<Blob>(resolve => { finish = resolve }))
  const view = setup(api)
  fireEvent.click(screen.getByRole('button', { name: 'Открыть скриншот' }))
  view.unmount()
  await act(async () => { finish(new Blob(['TEST'], { type: 'image/png' })) })
  expect(makeUrl).not.toHaveBeenCalled()
})

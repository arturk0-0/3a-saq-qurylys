import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { AuthContext } from '@/features/auth/AuthProvider'
import { MaterialHistory } from './MaterialHistory'

it('loads history only on demand, paginates on the server and shows a role instead of an absent display name', async () => {
  const api = vi.fn(async (path: string) => ({ items: [{ id: 'event', action: 'material.review', createdAt: '2026-10-20T10:00:00Z',
    reviewerDisplayName: null, actorUid: 'PRIVATE-UID-MUST-NOT-DISPLAY', details: { notes: path.includes('cursor=') ? 'Ранее сохранённое решение' : 'Проверено по оригиналу', disposition: 'reviewed' } }], nextCursor: path.includes('cursor=') ? null : 'older-page' }))
  render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api: api as never, signIn: vi.fn(), logout: vi.fn() }}><MaterialHistory id="m1" version={2} /></AuthContext.Provider>)
  expect(api).not.toHaveBeenCalled()
  fireEvent.click(screen.getByText('История проверок материала'))
  await screen.findByText('Проверено по оригиналу')
  expect(screen.getByText(/Аналитик/)).not.toHaveTextContent('PRIVATE-UID')
  expect(document.body.textContent).not.toContain('PRIVATE-UID-MUST-NOT-DISPLAY')
  fireEvent.click(screen.getByRole('button', { name: 'Следующие проверки' }))
  await screen.findByText('Ранее сохранённое решение')
  await waitFor(() => expect(api).toHaveBeenLastCalledWith('/api/v1/materials/m1/history?limit=20&cursor=older-page', expect.anything()))
})

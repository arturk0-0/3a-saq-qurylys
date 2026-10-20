import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { AuthContext } from '@/features/auth/AuthProvider'
import { LegacyAdvertisingRedirect } from './LegacyAdvertising'

function Destination() { const location = useLocation(); return <p>{location.pathname + location.search}</p> }
function setup(kind: 'advertisement' | 'monitoring', entry: string, fail = false) {
  const api = vi.fn(async () => { if (fail) throw new Error('Источник недоступен'); return { id: 'canonical-material' } })
  render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api: api as never, signIn: vi.fn(), logout: vi.fn() }}>
    <MemoryRouter initialEntries={[entry]}><Routes>
      <Route path="/advertisements/:id" element={<LegacyAdvertisingRedirect kind={kind} />} />
      <Route path="/monitoring" element={<LegacyAdvertisingRedirect kind={kind} />} />
      <Route path="/advertising/materials/:id" element={<Destination />} />
    </Routes></MemoryRouter>
  </AuthContext.Provider>)
  return api
}

it('resolves an old advertisement to its exact material while preserving query parameters', async () => {
  const api = setup('advertisement', '/advertisements/old-ad?q=deposit')
  expect(await screen.findByText('/advertising/materials/canonical-material?q=deposit')).toBeInTheDocument()
  expect(api).toHaveBeenCalledWith('/api/v1/materials/old-ad', expect.anything())
})

it('resolves an old monitoring selection without guessing its material ID', async () => {
  const api = setup('monitoring', '/monitoring?item=old-finding&status=new')
  expect(await screen.findByText('/advertising/materials/canonical-material?item=old-finding&status=new')).toBeInTheDocument()
  expect(api).toHaveBeenCalledWith('/api/v1/materials/old-finding', expect.anything())
})

it('preserves an explicit archive fallback and retry when the material cannot be resolved', async () => {
  setup('advertisement', '/advertisements/old-ad?source=archive', true)
  expect(await screen.findByRole('alert')).toHaveTextContent('Источник недоступен')
  expect(screen.getByRole('link', { name: 'Открыть сохранённый оригинал и прежнюю историю →' })).toHaveAttribute('href', '/advertising/legacy/advertisement/old-ad?source=archive')
})

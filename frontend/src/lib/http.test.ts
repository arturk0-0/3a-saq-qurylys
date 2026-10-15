import { afterEach, expect, it, vi } from 'vitest'
import { createApiClient } from './http'
import { getHealth } from './api'

afterEach(() => vi.unstubAllEnvs())

it('uses the local proxy when no production origin is configured', async () => {
  vi.stubEnv('VITE_API_BASE_URL', '')
  const fetcher = vi.fn().mockResolvedValue(new Response('{"items":[]}', { headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', fetcher)
  await createApiClient(async () => 'test-token')('/api/v1/complexes')
  expect(fetcher.mock.calls[0][0]).toBe('/api/v1/complexes')
})

it('sends analyst requests and health to the configured Cloud Run origin', async () => {
  vi.stubEnv('VITE_API_BASE_URL', 'https://example.run.app/')
  const fetcher = vi.fn().mockImplementation(async () => new Response('{"status":"ok","service":"saq-qurylys-api"}', { headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', fetcher)
  await createApiClient(async () => 'test-token')('/api/v1/complexes?q=test')
  expect(fetcher.mock.calls[0][0]).toBe('https://example.run.app/api/v1/complexes?q=test')
  expect(fetcher.mock.calls[0][1].headers.get('Authorization')).toBe('Bearer test-token')
  await getHealth()
  expect(fetcher.mock.calls[1][0]).toBe('https://example.run.app/api/v1/health')
})

it.each(['https://example.run.app/api', 'https://user:pass@example.run.app', 'https://example.run.app?token=x', 'http://example.run.app', 'javascript:alert(1)'])(
  'rejects an invalid origin before obtaining or sending a token: %s', async (origin) => {
    vi.stubEnv('VITE_API_BASE_URL', origin)
    const token = vi.fn(), fetcher = vi.fn()
    vi.stubGlobal('fetch', fetcher)
    await expect(createApiClient(token)('/api/v1/me')).rejects.toThrow()
    expect(token).not.toHaveBeenCalled()
    expect(fetcher).not.toHaveBeenCalled()
  },
)

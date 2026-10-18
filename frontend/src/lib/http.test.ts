import { afterEach, expect, it, vi } from 'vitest'
import { ApiError, createApiClient } from './http'
import { getHealth } from './api'
import { errorMessage } from './labels'

it('does not suggest a blind retry when a provider collection reply is lost', async () => {
  vi.stubEnv('VITE_API_BASE_URL', '')
  const fetcher = vi.fn().mockRejectedValue(new TypeError('connection lost'))
  vi.stubGlobal('fetch', fetcher)
  const error = await createApiClient(async () => 'test-token')('/api/v1/monitoring/sources/s1/run', { method: 'POST' }).catch((value: unknown) => value)
  expect(errorMessage(error)).toMatch(/Проверьте историю запусков перед повтором/)
  expect(errorMessage(error)).toMatch(/поиск мог расходовать квоту/)
  expect(fetcher).toHaveBeenCalledTimes(1)
})

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

it.each([
  ['AI_MODEL_UNAVAILABLE', /модель Gemini недоступна/],
  ['AI_CREDENTIALS', /Ключ Gemini на сервере не принят/],
  ['AI_ACCESS_DENIED', /Gemini отклонил доступ/],
  ['AI_TIMEOUT', /не получен вовремя/],
  ['AI_NETWORK', /не смог связаться/],
  ['AI_TEMPORARY', /временно недоступен/],
  ['AI_REQUEST_REJECTED', /отклонил формат запроса/],
  ['FIRESTORE_INDEX_REQUIRED', /готовность индексов Firestore/],
  ['PDF_RENDER_FAILED', /Карточка сигнала сохранена/],
])('describes %s without exposing a server body and includes a safe support ID', async (code, expected) => {
  vi.stubEnv('VITE_API_BASE_URL', '')
  const requestId = '00000000-1111-2222-3333-444444444444'
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ code, requestId, message: 'PRIVATE PROVIDER KEY OR SOURCE' }), { status: 503 })))
  const error = await createApiClient(async () => 'test-token')('/api/v1/signals/s1/history').catch((value: unknown) => value)
  expect(error).toBeInstanceOf(ApiError)
  expect(errorMessage(error)).toMatch(expected)
  expect(errorMessage(error)).toContain(requestId)
  expect(errorMessage(error)).not.toContain('PRIVATE PROVIDER')
})

it.each([null, [], 'PRIVATE SOURCE', { code: 'toString', requestId: 'PRIVATE VALUE' }, { code: 'AI_MODEL_UNAVAILABLE', requestId: '<img src=x>' }])(
  'handles malformed error envelopes without rendering raw values: %j', async payload => {
    vi.stubEnv('VITE_API_BASE_URL', '')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), { status: 503 })))
    const error = await createApiClient(async () => 'test-token')('/api/v1/signals').catch((value: unknown) => value)
    expect(error).toBeInstanceOf(ApiError)
    expect(errorMessage(error)).not.toMatch(/PRIVATE|<img|function|Cannot read/)
  },
)

import { apiUrl } from './apiUrl'

export interface HealthResponse {
  status: 'ok'
  service: 'saq-qurylys-api'
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(apiUrl('/api/v1/health'), { signal })
  if (!response.ok) throw new Error('API недоступен. Проверьте запуск backend.')
  const data: unknown = await response.json()
  if (typeof data !== 'object' || data === null || !('status' in data) ||
      !('service' in data) || data.status !== 'ok' || data.service !== 'saq-qurylys-api') {
    throw new Error('API вернул неожиданный ответ.')
  }
  return data as HealthResponse
}

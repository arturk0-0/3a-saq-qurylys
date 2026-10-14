export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public requestId?: string) {
    super(message)
  }
}

export type ApiClient = <T>(path: string, init?: RequestInit) => Promise<T>

export function createApiClient(getToken: () => Promise<string>): ApiClient {
  return async <T>(path: string, init: RequestInit = {}): Promise<T> => {
    if (!path.startsWith('/api/v1/')) throw new Error('Invalid API path')
    const headers = new Headers(init.headers)
    headers.set('Authorization', `Bearer ${await getToken()}`)
    if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
    const timeout = AbortSignal.timeout(20000)
    const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout
    let response: Response
    try {
      response = await fetch(path, { ...init, headers, signal })
    } catch (error) {
      if (init.signal?.aborted) throw error
      throw new ApiError(0, 'NETWORK_ERROR', 'Нет связи с сервером. Проверьте подключение и повторите.')
    }
    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      const message = response.status === 401 ? 'Сессия истекла. Войдите снова.'
        : response.status === 403 ? 'Недостаточно прав для этого действия.'
        : response.status === 503 ? 'Сервис временно недоступен или ещё не настроен.'
        : response.status === 409 ? 'Данные изменились. Обновите страницу и повторите действие.'
        : 'Не удалось выполнить запрос. Проверьте данные и повторите.'
      throw new ApiError(response.status, typeof error.code === 'string' ? error.code : 'REQUEST_FAILED',
        message, typeof error.requestId === 'string' ? error.requestId : undefined)
    }
    return response.json() as Promise<T>
  }
}

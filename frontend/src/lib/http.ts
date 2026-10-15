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
    if (init.body && !(init.body instanceof FormData) && !(init.body instanceof Blob)) headers.set('Content-Type', 'application/json')
    const timeout = AbortSignal.timeout(path.endsWith('/analyze') ? 90000 : 40000)
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
      const knownMessages: Record<string, string> = {
        AI_DAILY_LIMIT: 'Достигнут дневной лимит анализов. Повторите в следующие сутки UTC.',
        AI_PROVIDER_QUOTA: 'Лимит Gemini исчерпан. Повторите позже или проверьте квоту проекта.',
        AI_INVALID_RESPONSE: 'Ответ Gemini не прошёл проверку. Гипотезы не сохранены; исходный материал доступен.',
        INVALID_IMAGE: 'Выберите корректный статичный JPEG, PNG или WebP до 20 мегапикселей.',
        FILE_INTEGRITY: 'Контрольная сумма файла не совпала. Обратитесь к администратору.',
        FACTOR_NOT_SUPPORTED: 'Источники не подтверждают этот фактор. Проверьте тип доказательства и отмеченные факты.',
        EXCERPT_MISMATCH: 'Цитата должна точно совпадать с фрагментом оригинального объявления.',
        SOURCE_MISMATCH: 'Ссылка должна совпадать с оригинальным объявлением.',
        PDF_BUSY: 'Генератор PDF занят. Повторите через несколько секунд.',
        EXPIRED_BASIS: 'Нельзя подтвердить основание с истёкшим сроком действия.',
      }
      const message = knownMessages[error.code] || (response.status === 401 ? 'Сессия истекла. Войдите снова.'
        : response.status === 403 ? 'Недостаточно прав для этого действия.'
        : response.status === 503 ? 'Сервис временно недоступен или ещё не настроен.'
        : response.status === 409 ? 'Данные изменились. Обновите страницу и повторите действие.'
        : response.status === 429 ? 'Достигнут лимит AI-запросов. Повторите позже.'
        : response.status === 413 ? 'Файл слишком большой. Максимум — 6 МБ.'
        : response.status === 502 ? 'Внешний сервис вернул некорректный результат. Данные не подтверждены.'
        : 'Не удалось выполнить запрос. Проверьте данные и повторите.')
      throw new ApiError(response.status, typeof error.code === 'string' ? error.code : 'REQUEST_FAILED',
        message, typeof error.requestId === 'string' ? error.requestId : undefined)
    }
    if (response.headers.get('content-type')?.includes('application/json')) return response.json() as Promise<T>
    return response.blob() as Promise<T>
  }
}

import { apiUrl } from './apiUrl'

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public requestId?: string) {
    super(message)
  }
}

export type ApiClient = <T>(path: string, init?: RequestInit) => Promise<T>

export function createApiClient(getToken: () => Promise<string>): ApiClient {
  return async <T>(path: string, init: RequestInit = {}): Promise<T> => {
    const url = apiUrl(path)
    const headers = new Headers(init.headers)
    headers.set('Authorization', `Bearer ${await getToken()}`)
    if (init.body && !(init.body instanceof FormData) && !(init.body instanceof Blob)) headers.set('Content-Type', 'application/json')
    const timeout = AbortSignal.timeout(path.endsWith('/analyze') ? 90000 : 40000)
    const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout
    let response: Response
    try {
      response = await fetch(url, { ...init, headers, signal })
    } catch (error) {
      if (init.signal?.aborted) throw error
      throw new ApiError(0, 'NETWORK_ERROR', 'Нет связи с сервером. Проверьте подключение и повторите.')
    }
    if (!response.ok) {
      const payload: unknown = await response.json().catch(() => null)
      const error = payload && typeof payload === 'object' ? payload as Record<string, unknown> : {}
      const code = typeof error.code === 'string' && /^[A-Z][A-Z0-9_]{0,63}$/.test(error.code) ? error.code : 'REQUEST_FAILED'
      const knownMessages: Record<string, string> = {
        AI_DAILY_LIMIT: 'Достигнут дневной лимит анализов. Повторите в следующие сутки UTC.',
        AI_PROVIDER_QUOTA: 'Лимит Gemini исчерпан. Повторите позже или проверьте квоту проекта.',
        AI_NOT_CONFIGURED: 'AI ещё не настроен. Попросите администратора проверить модель и ключ Gemini на сервере.',
        AI_CREDENTIALS: 'Ключ Gemini на сервере не принят. Администратору нужно проверить ключ; повторный анализ пока не запускайте.',
        AI_ACCESS_DENIED: 'Gemini отклонил доступ. Администратору нужно проверить доступ к API и ограничения серверного ключа.',
        AI_MODEL_UNAVAILABLE: 'Выбранная модель Gemini недоступна для анализа. Администратору нужно выбрать доступную модель на сервере.',
        AI_TIMEOUT: 'Ответ Gemini не получен вовремя. Обновите результаты перед новым запуском: повтор может расходовать квоту.',
        AI_NETWORK: 'Сервер не смог связаться с Gemini. Обновите результаты и повторите позже.',
        AI_TEMPORARY: 'Gemini временно недоступен. Исходный материал сохранён; повторите позже.',
        AI_REQUEST_REJECTED: 'Gemini отклонил формат запроса. Передайте код обращения администратору.',
        FIRESTORE_INDEX_REQUIRED: 'История или список пока недоступны: администратору нужно проверить готовность индексов Firestore.',
        PDF_RENDER_FAILED: 'Не удалось сформировать PDF. Карточка сигнала сохранена; повторите позже или используйте печать карточки.',
        AI_INVALID_RESPONSE: 'Ответ Gemini не прошёл проверку. Гипотезы не сохранены; исходный материал доступен.',
        INVALID_IMAGE: 'Выберите корректный статичный JPEG, PNG или WebP до 20 мегапикселей.',
        FILE_INTEGRITY: 'Контрольная сумма файла не совпала. Обратитесь к администратору.',
        FACTOR_NOT_SUPPORTED: 'Источники не подтверждают этот фактор. Проверьте тип доказательства и отмеченные факты.',
        EXCERPT_MISMATCH: 'Цитата должна точно совпадать с фрагментом оригинального объявления.',
        SOURCE_MISMATCH: 'Ссылка должна совпадать с оригинальным объявлением.',
        TRACE_STALE: 'Исходное объявление изменилось. Обновите совпадения и проверьте новый материал; обоснование сохранено в форме.',
        TRACE_NO_MATCH: 'Поддержанное совпадение больше не найдено. Обновите список и проверьте оригиналы.',
        TRACE_TOO_MANY_IDENTIFIERS: 'В тексте слишком много контактов для полной проверки. Требуется отдельная проверка оригинала.',
        PDF_BUSY: 'Генератор PDF занят. Повторите через несколько секунд.',
        EXPIRED_BASIS: 'Нельзя подтвердить основание с истёкшим сроком действия.',
      }
      const message = (Object.hasOwn(knownMessages, code) ? knownMessages[code] : undefined) || (response.status === 401 ? 'Сессия истекла. Войдите снова.'
        : response.status === 403 ? 'Недостаточно прав для этого действия.'
        : response.status === 503 ? 'Сервис временно недоступен или ещё не настроен.'
        : response.status === 409 ? 'Данные изменились. Обновите страницу и повторите действие.'
        : response.status === 429 ? 'Достигнут лимит AI-запросов. Повторите позже.'
        : response.status === 413 ? 'Файл слишком большой. Максимум — 6 МБ.'
        : response.status === 502 ? 'Внешний сервис вернул некорректный результат. Данные не подтверждены.'
        : 'Не удалось выполнить запрос. Проверьте данные и повторите.')
      throw new ApiError(response.status, code, message,
        typeof error.requestId === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(error.requestId) ? error.requestId : undefined)
    }
    if (response.headers.get('content-type')?.includes('application/json')) return response.json() as Promise<T>
    return response.blob() as Promise<T>
  }
}

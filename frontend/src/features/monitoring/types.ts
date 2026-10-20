export interface Source {
  id: string; name: string; kind: 'web_search' | 'telegram' | 'instagram_ads'; target: string;
  intervalMinutes: number; autoAnalyze: boolean; enabled: boolean; version: number;
  lastRunAt: string | null; nextRunAt: string | null; leaseUntil: string | null;
  lastError: string | null;
}
export interface MonitorStatus {
  workerLastTickAt: string | null; dailyFetchUsed: number; dailyFetchLimit: number;
  maxAutoAiPerRun: number; liveRegistryEnabled: boolean;
  instagramTargetedAds: 'not_connected' | 'configured';
  searchApi?: { scheduled: boolean; dailyLimit: number; dailyUsed: number; creditReserve: number;
    creditsObservedBefore: number | null; checkedAt: string | null; unsettledAttempts: number };
}
export interface Finding {
  id: string; title: string; text: string; originalUrl: string; discoveryUrl: string;
  contentKind: 'search_snippet' | 'telegram_post' | 'instagram_ad'; account: string;
  adArchiveId?: string | null; adStartedAt?: string | null; adActive?: boolean | null;
  platforms?: string[]; media?: { kind: 'image' | 'video' | 'thumbnail'; url: string }[];
  createdAt: string; lastSeenAt: string; publishedAt: string | null;
  regionMatches: string[]; housingMatches: string[]; paymentMatches: string[];
  textSha256: string; responseSha256: string; revisionKey: string; sourceIds: string[];
  status: 'new' | 'investigating' | 'dismissed'; notes: string; version: number;
  reviewer: string | null; reviewedAt: string | null;
  aiStatus: 'not_requested' | 'running' | 'succeeded' | 'failed';
  aiError: string | null; aiModel: string | null;
  extraction: { hypotheses: { code: 'R2' | 'R3'; quote: string; explanation: string }[];
    uncertainty: string; paymentTerms: string[] } | null;
  advertisementId: string | null;
  basisReview?: BasisReview | null;
}
export interface Run {
  id: string; sourceId: string; status: string; createdAt: string; completedAt: string | null;
  fetched: number; relevant: number; created: number; duplicates: number;
  limited: boolean; errorCode: string | null; autoAiStatus: string | null;
  unreadable?: number; providerCreditsBefore?: number | null;
}
export interface Page<T> { items: T[]; nextCursor: string | null }
export const findingLabels = { new: 'Новая находка', investigating: 'В работе эксперта', dismissed: 'Отложено экспертом' };
export const monitorErrors: Record<string, string> = {
  SEARCHAPI_DISABLED: 'Instagram-сбор выключен на сервере. Сохранённые находки доступны.',
  SEARCHAPI_NOT_CONFIGURED: 'Ключ SearchAPI ещё не настроен на сервере.',
  SEARCHAPI_RESERVE: 'Сбор остановлен: сохраняем минимум 20 запросов для хакатона. Неопределённые попытки тоже учитываются.',
  SEARCHAPI_DAILY_LIMIT: 'Достигнут дневной лимит поисков Instagram. Новые попытки — в следующие сутки UTC.',
  SEARCHAPI_BUSY: 'Другой поиск Instagram уже выполняется. Проверьте историю перед новой попыткой.',
  SEARCHAPI_CREDENTIALS: 'SearchAPI не принял серверный ключ или доступ. Повтор пока не запускайте.',
  SEARCHAPI_QUOTA: 'SearchAPI ограничил запросы. Проверьте остаток и тариф.',
  SEARCHAPI_TEMPORARY: 'SearchAPI временно недоступен. Автоматического повтора нет.',
  SEARCHAPI_FORMAT: 'Не удалось проверить ответ или остаток SearchAPI. Сбор остановлен.',
  SEARCHAPI_NETWORK: 'Нет связи с SearchAPI. Проверьте историю перед повтором.',
  SEARCHAPI_TIMEOUT: 'Истекло время ожидания SearchAPI. Повтор может расходовать запрос.',
  SEARCHAPI_SIZE: 'Ответ SearchAPI превышает лимит обработки.',
  MONITOR_SOURCE_BLOCKED: 'Источник ограничил доступ или частоту запросов.',
  MONITOR_SOURCE_HTTP: 'Источник недоступен или перенаправляет запрос.',
  MONITOR_SOURCE_NETWORK: 'Нет связи с источником.',
  MONITOR_SOURCE_TIMEOUT: 'Источник не ответил в установленное время.',
  MONITOR_SOURCE_FORMAT: 'Не удалось прочитать публикации. Источник мог изменить формат.',
  MONITOR_SOURCE_SIZE: 'Страница превышает лимит сбора.',
  MONITOR_LEASE_LOST: 'Запуск прерван; источник обрабатывает другой worker.',
  MONITOR_LEASE_EXPIRED: 'Предыдущий запуск был прерван; срок его блокировки истёк.',
  AI_NOT_CONFIGURED: 'Gemini не настроен.', AI_MODEL_UNAVAILABLE: 'Модель недоступна.',
  AI_DAILY_LIMIT: 'Достигнут суточный лимит Gemini.', AI_INVALID_RESPONSE: 'Ответ Gemini не прошёл проверку.',
};
export function safeMonitorError(code: string | null) { return code ? monitorErrors[code] || 'Операция не завершена. Код: ' + code : '' }
export function contentLabel(kind: Finding['contentKind']) {
  return kind === 'instagram_ad' ? 'Instagram · Meta Ad Library' : kind === 'telegram_post' ? 'Telegram' : 'Фрагмент поиска'
}

export interface RegistryDocument {
  provider: 'homeportal'; recordId: string; kind: 'regional_permit' | 'guarantee';
  name: string; address: string; developer: string; developerBin: string;
  holder: string; holderBin: string; reference: string; issuedOn: string;
  sourceUrl: string; responseSha256: string; documentSha256: string; checkedAt: string;
}
export interface BasisReview {
  document: RegistryDocument; advertisementDate: string;
  reviewer: string; reviewedAt: string; notes: string;
}
export interface RegistryCandidate {
  provider: string; recordId: string; name: string; address: string;
  developer: string; developerBin: string; holder: string; holderBin: string;
  basisLabel: string; reference: string; sourceUrl: string; dataAsOf: string | null;
}
export interface RegistrySearch {
  checkedAt: string; sources: { provider: string; status: 'ok' | 'unavailable';
    candidates: RegistryCandidate[]; limited: boolean; errorCode?: string }[];
}

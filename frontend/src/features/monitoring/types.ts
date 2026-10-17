export interface Source {
  id: string; name: string; kind: 'web_search' | 'telegram'; target: string;
  intervalMinutes: number; autoAnalyze: boolean; enabled: boolean; version: number;
  lastRunAt: string | null; nextRunAt: string | null; leaseUntil: string | null;
  lastError: string | null;
}
export interface MonitorStatus {
  workerLastTickAt: string | null; dailyFetchUsed: number; dailyFetchLimit: number;
  maxAutoAiPerRun: number; liveRegistryEnabled: boolean;
  instagramTargetedAds: 'not_connected';
}
export interface Finding {
  id: string; title: string; text: string; originalUrl: string; discoveryUrl: string;
  contentKind: 'search_snippet' | 'telegram_post'; account: string;
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
}
export interface Run {
  id: string; sourceId: string; status: string; createdAt: string; completedAt: string | null;
  fetched: number; relevant: number; created: number; duplicates: number;
  limited: boolean; errorCode: string | null; autoAiStatus: string | null;
}
export interface Page<T> { items: T[]; nextCursor: string | null }
export const findingLabels = { new: 'Новая находка', investigating: 'В работе эксперта', dismissed: 'Отложено экспертом' };
export const monitorErrors: Record<string, string> = {
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


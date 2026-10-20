export type Criterion = { id: string; label: string; sourceUrl: string | null }
export type Observation = { criterionId: string; visibility: 'visible' | 'not_visible' | 'uncertain'; explanation: string }
export type DroneResult = { observations: Observation[]; summary: string; limitations: string }
export type DroneRun = { id: string; status: 'running' | 'succeeded' | 'failed'; createdAt: string; completedAt?: string;
  model: string; promptVersion: string; checklist: Criterion[]; result: DroneResult | null; errorCode: string | null }
export type Review = { runId: string; decision: 'accepted' | 'needs_followup' | 'rejected'; notes: string; reviewer: string; reviewedAt: string }
export type Inspection = { id: string; title: string; complexId: string | null; complexName: string | null; capturedAt: string | null;
  version: number; createdAt: string; checklist: Criterion[]; status: 'awaiting_photo' | 'ready' | 'analyzing' | 'analyzed' | 'failed' | 'reviewed';
  photo: { id: string; mediaType: string; sha256: string; sizeBytes: number; uploadedAt: string } | null;
  reviews: Review[]; latestRunId: string | null; latestRun: DroneRun | null; canAnalyze: boolean; analysisCount: number; lastError: string | null }
export const visibilityLabels = { visible: 'Видно на снимке', not_visible: 'Не видно в кадре', uncertain: 'Нельзя определить' }
export const reviewLabels = { accepted: 'Наблюдения рассмотрены', needs_followup: 'Требуется дополнительный осмотр', rejected: 'Результат ИИ отклонён' }
export const statusLabels: Record<Inspection['status'], string> = { awaiting_photo: 'Ожидает фотографию', ready: 'Готово к анализу', analyzing: 'Анализ выполняется', analyzed: 'Ожидает решения эксперта', failed: 'Анализ не завершён', reviewed: 'Рассмотрено экспертом' }
export function validPhoto(file: File) { return file.size > 0 && file.size <= 6 * 1024 * 1024 && ['image/jpeg', 'image/png', 'image/webp'].includes(file.type) }
export function safeReference(value: string) { try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : null } catch { return null } }

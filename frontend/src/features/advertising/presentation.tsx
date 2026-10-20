import { Link } from 'react-router-dom'
import type { Priority } from '@/lib/types'
import { formatDate } from '@/lib/labels'
import { monitorErrors } from '@/features/monitoring/types'
import type { Analysis, ReviewState } from './types'

export const reviewLabels: Record<ReviewState, string> = { needs_review: 'Требует проверки', reviewed: 'Проверено', dismissed: 'Отложено' }
const levels = { unknown: 'Ещё не оценено', low: 'Низкий', medium: 'Средний', high: 'Высокий' }
export function PriorityView({ value }: { value?: Priority | null }) {
  const calculated = value && value.score !== null
  return <div className="ad-priority"><strong>Приоритет проверки: {calculated ? `${levels[value.level]} · ${value.score}` : 'Ещё не оценено'}</strong>
    <p className="form-hint">Предварительная оценка очереди, не подтверждённый риск.</p>
    {value?.reasons.length ? <ul>{value.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul> : null}</div>
}
export function AnalysisView({ value }: { value: Analysis }) {
  const text = value.status === 'queued' ? value.errorCode === 'AI_DAILY_LIMIT' ? 'Ожидает доступной квоты анализа' : 'Ожидает автоматического анализа'
    : value.status === 'running' ? 'Автоматический анализ выполняется'
    : value.status === 'ready' ? 'Анализ готов — требуется решение человека'
    : value.status === 'unsupported' ? 'Автоанализ этого формата недоступен' : 'Анализ не выполнен'
  return <div className="ad-analysis-state" role="status"><strong>{text}</strong>
    {value.status === 'unsupported' && <p>Откройте оригинал и проверьте материал вручную. Ссылка или превью не означают, что видео просмотрено.</p>}
    {value.errorCode && <p>{monitorErrors[value.errorCode] || 'Материал сохранён. Автоматического подтверждения нет.'}</p>}
    {value.updatedAt && <p className="form-hint">Обновлено {formatDate(value.updatedAt)}</p>}</div>
}
export function AdvertisingTabs({ selected }: { selected: 'materials' | 'sources' }) {
  return <nav className="ad-tabs" aria-label="Разделы рекламы">
    <Link to="/advertising" aria-current={selected === 'materials' ? 'page' : undefined}>Все материалы</Link>
    <Link to="/advertising?view=sources" aria-current={selected === 'sources' ? 'page' : undefined}>Источники и расписание</Link>
  </nav>
}
export function safeExternal(url: string | null): string | null {
  if (!url) return null
  try { const parsed = new URL(url); return ['https:', 'http:'].includes(parsed.protocol) && !parsed.username && !parsed.password ? parsed.href : null } catch { return null }
}

import { formatDate } from '@/lib/labels'
import type { Citation } from './types'

export function safeWebUrl(value: string) {
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null } catch { return null }
}
export function CitationLink({ source }: { source: Citation }) {
  const href = safeWebUrl(source.url)
  if (!href) return <small>Источник недоступен</small>
  return <a className="company-citation" href={href} target="_blank" rel="noopener noreferrer"
    title={'Получено ' + formatDate(source.retrievedAt) + (source.effectiveDate ? '; сведения на ' + source.effectiveDate : '; дата сведений не указана')}>
    {source.publisher} ↗<span className="sr-only"> · источник значения, получено {formatDate(source.retrievedAt)}</span>
  </a>
}

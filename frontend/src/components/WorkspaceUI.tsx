import { cloneElement, isValidElement, useEffect, useId, useRef, type ReactNode } from 'react'
import { AlertCircle, ArrowRight, LoaderCircle } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { statusLabels } from '@/lib/labels'
import type { RiskResult, VerificationStatus } from '@/lib/types'

export function PageHeading({ eyebrow, title, description, action }: {
  eyebrow: string; title: string; description: string; action?: ReactNode
}) {
  return <div className="page-heading"><div><p className="eyebrow">{eyebrow}</p>
    <h1>{title}</h1><p className="page-description">{description}</p></div>{action}</div>
}
export function LoadingState() {
  return <div className="state-box" role="status"><LoaderCircle className="animate-spin" size={22} /> Загружаем данные…</div>
}
export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="state-box error-box" role="alert"><AlertCircle size={22} /><p>{message}</p>
    {retry && <Button type="button" variant="outline" onClick={retry}>Повторить</Button>}</div>
}
export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="state-box flex-col"><h2 className="font-semibold">{title}</h2>{children}</div>
}
export function RiskBadge({ risk }: { risk: Pick<RiskResult, 'score' | 'zone'> }) {
  const label = { GREEN: 'Низкий приоритет', YELLOW: 'Требует проверки', RED: 'Высокий приоритет' }[risk.zone]
  return <span className={`risk-badge risk-${risk.zone.toLowerCase()}`}><span className="risk-dot" />{risk.score} · {label}</span>
}
export function StatusBadge({ status, label }: { status: VerificationStatus; label?: string }) {
  return <span className={`status-badge status-${status}`}>{label || statusLabels[status]}</span>
}
export function DetailLink({ to, children }: { to: string; children: ReactNode }) {
  return <Link to={to} className="detail-link">{children}<ArrowRight size={15} /></Link>
}
export function FormField({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  const generatedId = useId()
  if (!isValidElement<{ id?: string; 'aria-describedby'?: string }>(children)) return <label className="form-field"><span>{label}</span>{children}</label>
  const id = children.props.id || generatedId
  const describedBy = [children.props['aria-describedby'], hint ? `${id}-hint` : null].filter(Boolean).join(' ') || undefined
  return <div className="form-field"><label htmlFor={id}>{label}</label>{cloneElement(children, { id, 'aria-describedby': describedBy })}{hint && <small id={`${id}-hint`}>{hint}</small>}</div>
}

export function EditorHeading({ children }: { children: ReactNode }) {
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    heading.current?.focus({ preventScroll: true })
    heading.current?.scrollIntoView?.({ block: 'start' })
  }, [])
  return <h3 ref={heading} tabIndex={-1} className="editor-heading">{children}</h3>
}

export function ReviewGuide() {
  return <section className="review-guide" aria-label="Порядок проверки">
    <ol><li><strong>1. Гипотеза AI</strong><span>Цитата для проверки</span></li><li><strong>2. Проверка источника</strong><span>Аналитик сверяет оригинал</span></li><li><strong>3. Решение по фактору</strong><span>Отдельное подтверждение R1–R6</span></li><li><strong>4. Сигнал и PDF</strong><span>Отдельное решение аналитика</span></li></ol>
    <p>AI необязателен. Принятие гипотезы и проверка источника сами по себе не меняют баллы. Оценку пересчитывает сервер после решения по фактору.</p>
  </section>
}

export function EvidenceProvenance({ reference }: { reference?: string }) {
  if (!reference) return null
  if (!reference.startsWith('AI hypothesis; ')) return <p className="form-hint">{reference}</p>
  return <div className="form-hint"><p>В реквизитах указан AI-анализ. Текущий статус проверки источника показан отдельно.</p><details><summary>Происхождение и версия анализа</summary><p>{reference}</p><p>Отметка «unverified» относится к моменту создания гипотезы и не заменяет последующее решение аналитика.</p></details></div>
}

export function ScrollableTable({ label, children }: { label: string; children: ReactNode }) {
  const hintId = useId()
  return <><p id={hintId} className="sr-only">Если таблица не помещается, прокручивайте её по горизонтали клавишами со стрелками.</p><div className="table-scroll" role="region" aria-label={label} aria-describedby={hintId} tabIndex={0}>{children}</div></>
}
export function DemoBadge() { return <span className="demo-badge">DEMO</span> }
export function SourceLink({ url }: { url: string | null }) {
  if (!url) return null
  try { if (!['http:', 'https:'].includes(new URL(url).protocol)) return <span>Недопустимая ссылка</span> }
  catch { return <span>Недопустимая ссылка</span> }
  return <a href={url} target="_blank" rel="noopener noreferrer" className="source-link">Открыть источник ↗</a>
}

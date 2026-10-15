import type { ReactNode } from 'react'
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
    {retry && <Button variant="outline" onClick={retry}>Повторить</Button>}</div>
}
export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="state-box flex-col"><h2 className="font-semibold">{title}</h2>{children}</div>
}
export function RiskBadge({ risk }: { risk: Pick<RiskResult, 'score' | 'zone'> }) {
  const label = { GREEN: 'Низкий приоритет', YELLOW: 'Требует проверки', RED: 'Высокий приоритет' }[risk.zone]
  return <span className={`risk-badge risk-${risk.zone.toLowerCase()}`}><span className="risk-dot" />{risk.score} · {label}</span>
}
export function StatusBadge({ status }: { status: VerificationStatus }) {
  return <span className={`status-badge status-${status}`}>{statusLabels[status]}</span>
}
export function DetailLink({ to, children }: { to: string; children: ReactNode }) {
  return <Link to={to} className="detail-link">{children}<ArrowRight size={15} /></Link>
}
export function FormField({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return <label className="form-field"><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>
}
export function DemoBadge() { return <span className="demo-badge">DEMO</span> }
export function SourceLink({ url }: { url: string | null }) {
  if (!url) return null
  try { if (!['http:', 'https:'].includes(new URL(url).protocol)) return <span>Недопустимая ссылка</span> }
  catch { return <span>Недопустимая ссылка</span> }
  return <a href={url} target="_blank" rel="noopener noreferrer" className="source-link">Открыть источник ↗</a>
}

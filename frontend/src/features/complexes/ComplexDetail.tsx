import { ProjectParties } from '@/features/companies/ProjectParties'
import { ActorName } from '@/components/ActorName'
import { useState, type FormEvent, type KeyboardEvent } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft, MapPin } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { DemoBadge, EmptyState, ErrorState, FormField, LoadingState, PageHeading, ReviewGuide } from '@/components/WorkspaceUI'
import { AdvertisementCard, AdvertisementForm } from '@/features/advertisements/AdvertisementsPage'
import { useAuth } from '@/features/auth/AuthProvider'
import { basisLabels, formatDate, localDateTime, stageLabels } from '@/lib/labels'
import { useApiQuery } from '@/lib/useApiQuery'
import { useReviewRecord } from '@/lib/useReviewRecord'
import type { Advertisement, AuditEvent, Complex, Page } from '@/lib/types'
import { EvidencePanel } from './EvidencePanel'
import { RiskPanel } from './RiskPanel'
import { PublicSources } from './PublicSources'

function ComplexAdvertisements({ id }: { id: string }) {
  const [creating, setCreating] = useState(false)
  const [cursor, setCursor] = useState('')
  const { data, loading, error, refresh } = useApiQuery<Page<Advertisement>>(`/api/v1/complexes/${id}/advertisements?limit=50${cursor ? `&cursor=${cursor}` : ''}`)
  return <><div className="panel-heading"><h2>Объявления по объекту</h2><Button variant="outline" onClick={() => setCreating(true)}>Добавить</Button></div>
    {creating && <AdvertisementForm complexId={id} onCancel={() => setCreating(false)} onSaved={() => { setCreating(false); setCursor(''); refresh() }} />}
    {loading ? <LoadingState /> : error ? <ErrorState message={error} retry={refresh} /> : !data?.items.length ? <EmptyState title="Объявлений пока нет" />
      : data.items.map((ad) => <AdvertisementCard key={ad.id} ad={ad} />)}
    {(cursor || data?.nextCursor) && <div className="pagination"><Button variant="outline" onClick={() => setCursor('')}>В начало</Button>{data?.nextCursor && <Button variant="outline" onClick={() => setCursor(data.nextCursor!)}>Далее</Button>}</div>}
  </>
}

function DocumentsPanel({ complex_: initialComplex, onChanged }: { complex_: Complex; onChanged: () => void }) {
  const { api } = useAuth()
  const record = useReviewRecord(initialComplex, `/api/v1/complexes/${initialComplex.id}`)
  const complex_ = record.current
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const error = record.error
  const basis = complex_.legalBasis
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setBusy(true); record.clearError()
    try {
      await api(`/api/v1/complexes/${complex_.id}/legal-basis`, { method: 'PATCH', body: JSON.stringify({
        basis: { type: form.get('type'), status: form.get('status'), reference: form.get('reference'), source: form.get('source'),
          validUntil: form.get('validUntil') ? new Date(String(form.get('validUntil'))).toISOString() : null }, expectedVersion: complex_.version,
      }) })
      setEditing(false); onChanged()
    } catch (error) { record.failed(error) } finally { setBusy(false) }
  }
  return <div className="content-pad"><div className="flex items-center justify-between gap-3"><h2>Правовое основание</h2><Button variant="outline" onClick={() => setEditing(!editing)}>Пересмотреть</Button></div>
    <dl className="details-grid"><div><dt>Тип</dt><dd>{basisLabels[basis.type]}</dd></div><div><dt>Статус</dt><dd>{{ unknown: 'Не проверено', confirmed: 'Подтверждено', disproved: 'Опровергнуто' }[basis.status]}</dd></div>
      <div><dt>Реквизиты</dt><dd>{basis.reference || 'Не указаны'}</dd></div><div><dt>Проверено</dt><dd>{formatDate(basis.checkedAt)}</dd></div><div className="col-span-full"><dt>Источник</dt><dd>{basis.source || 'Нет источника'}</dd></div></dl>
    <p className="inline-notice">Неизвестное основание не означает его отсутствие. Действующая применимая гарантия может служить правовым основанием.</p>
    {editing && <form className="editor-form" onSubmit={submit}><div className="form-grid">
      <FormField label="Тип основания"><select name="type" defaultValue={basis.type}>{Object.entries(basisLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></FormField>
      <FormField label="Статус проверки"><select name="status" defaultValue={basis.status}><option value="unknown">Не проверено</option><option value="confirmed">Подтверждено</option><option value="disproved">Опровергнуто</option></select></FormField>
    </div><FormField label="Реквизиты"><input name="reference" defaultValue={basis.reference} maxLength={500} /></FormField><FormField label="Источник проверки"><textarea name="source" defaultValue={basis.source} rows={3} maxLength={2000} /></FormField>
      <FormField label="Действует до (если указано)"><input name="validUntil" type="datetime-local" defaultValue={localDateTime(basis.validUntil)} /></FormField>
      {complex_.version !== initialComplex.version && <p className="inline-notice">Актуальная версия ЖК: {complex_.version}. Текущие сведения показаны выше. Ваши поля сохранены; сверьте их перед повторным решением.</p>}
      {error && <ErrorState message={error} />}
      {record.conflict && <Button type="button" variant="outline" disabled={record.refreshing} onClick={() => { void record.refresh() }}>{record.refreshing ? 'Обновляем данные…' : 'Обновить данные ЖК'}</Button>}
      <div className="form-actions"><Button disabled={busy || record.conflict || record.refreshing}>Сохранить проверку</Button><Button type="button" variant="outline" disabled={busy || record.refreshing} onClick={() => setEditing(false)}>Отмена</Button></div></form>}
    <PublicSources complexId={complex_.id} demo={complex_.demo} />
  </div>
}

function HistoryPanel({ id }: { id: string }) {
  const [cursor, setCursor] = useState('')
  const { data, loading, error, refresh } = useApiQuery<Page<AuditEvent>>(`/api/v1/complexes/${id}/history?limit=100${cursor ? `&cursor=${cursor}` : ''}`)
  const actionLabels: Record<string, string> = { 'advertisement.create': 'Добавлено объявление', 'evidence.create': 'Добавлен источник', 'evidence.review': 'Проверен источник', 'factor.review': 'Пересмотрен фактор', 'basis.review': 'Проверено правовое основание', 'complex.create': 'Создан ЖК', 'adLink.propose': 'Сохранено рекламное совпадение', 'adLink.review': 'Проверено рекламное совпадение' }
  return <div className="content-pad"><h2>История действий</h2>{loading ? <LoadingState /> : error ? <ErrorState message={error} retry={refresh} /> : !data?.items.length ? <EmptyState title="Действий аналитиков пока нет" />
    : <ol className="timeline">{[...data.items].sort((a, b) => b.createdAt.localeCompare(a.createdAt)).map((event) => <li key={event.id} className="history-entry"><strong>{actionLabels[event.action] || event.action}</strong>
      <p>{formatDate(event.createdAt)} · <ActorName uid={event.actorUid} /></p>{typeof event.details.notes === 'string' && <blockquote>{event.details.notes}</blockquote>}
      {typeof event.details.beforeScore === 'number' && <small>Баллы: {event.details.beforeScore} → {String(event.details.afterScore)}</small>}</li>)}</ol>}
    {(cursor || data?.nextCursor) && <div className="pagination"><Button variant="outline" onClick={() => setCursor('')}>В начало</Button>{data?.nextCursor && <Button variant="outline" onClick={() => setCursor(data.nextCursor!)}>Далее</Button>}</div>}
  </div>
}

export function ComplexDetail() {
  const { id } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedTab = searchParams.get('tab') || 'overview'
  const tab = ['overview', 'ads', 'documents', 'evidence', 'history'].includes(requestedTab) ? requestedTab : 'overview'
  function setTab(value: string) { setSearchParams({ tab: value }) }
  const { data: complex_, loading, error, refresh } = useApiQuery<Complex>(id ? `/api/v1/complexes/${encodeURIComponent(id)}` : null)
  if (loading) return <LoadingState />
  if (error) return <ErrorState message={error} retry={refresh} />
  if (!complex_) return <EmptyState title="ЖК не найден" />
  const tabs = [['overview', 'Обзор'], ['ads', 'Объявления'], ['documents', 'Документы'], ['evidence', 'Доказательства'], ['history', 'История']]
  function navigateTabs(event: KeyboardEvent<HTMLDivElement>) {
    const current = tabs.findIndex(([key]) => key === tab)
    const next = { ArrowRight: (current + 1) % tabs.length, ArrowLeft: (current + tabs.length - 1) % tabs.length, Home: 0, End: tabs.length - 1 }[event.key]
    if (next === undefined) return
    event.preventDefault()
    setTab(tabs[next][0])
    event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus()
  }
  return <><Link to="/complexes" className="back-link"><ArrowLeft size={16} /> К реестру</Link>
    <PageHeading eyebrow={`Карточка объекта · ${complex_.city}`} title={complex_.name.replace(/^DEMO — /, '')} description={complex_.address} action={<div className="flex items-center gap-4">{complex_.demo && <DemoBadge />}<Link className="detail-link" to={`/signals/new?complex=${complex_.id}`}>Создать сигнал →</Link></div>} />
    <details className="review-help"><summary>Порядок проверки</summary><ReviewGuide /></details>
    <div className="detail-layout"><section className="panel min-w-0"><div className="tabs" role="tablist" aria-label="Разделы карточки" onKeyDown={navigateTabs}>{tabs.map(([key, label]) => <button key={key} type="button" role="tab" tabIndex={tab === key ? 0 : -1} aria-selected={tab === key} aria-controls={`panel-${key}`} id={`tab-${key}`} onClick={() => setTab(key)}>{label}</button>)}</div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === 'overview' && <div className="content-pad"><div className="object-illustration"><MapPin size={26} /><span>{complex_.city} · Восточно-Казахстанская область</span></div>
          <ProjectParties complex_={complex_} /><h2 className="mt-6">Сведения об объекте</h2><dl className="details-grid">
            <div><dt>Этап строительства</dt><dd>{stageLabels[complex_.stage]}</dd></div><div><dt>Регион</dt><dd>ВКО</dd></div></dl>

        </div>}
        {tab === 'ads' && <ComplexAdvertisements id={complex_.id} />}
        {tab === 'documents' && <DocumentsPanel complex_={complex_} onChanged={refresh} />}
        {tab === 'evidence' && <EvidencePanel complex_={complex_} onChanged={refresh} />}
        {tab === 'history' && <HistoryPanel id={complex_.id} />}
      </div>
    </section><RiskPanel complex_={complex_} onChanged={refresh} /></div>
  </>
}

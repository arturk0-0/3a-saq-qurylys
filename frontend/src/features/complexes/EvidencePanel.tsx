import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { EditorHeading, EmptyState, ErrorState, EvidenceProvenance, FormField, LoadingState, SourceLink, StatusBadge } from '@/components/WorkspaceUI'
import { useAuth } from '@/features/auth/AuthProvider'
import { errorMessage, formatDate, localDateTime } from '@/lib/labels'
import { useApiQuery } from '@/lib/useApiQuery'
import type { Advertisement, Complex, Evidence, Page } from '@/lib/types'
import { EvidenceFile } from './EvidenceFile'

const evidenceTypes = {
  advertisement: 'Текст объявления', legal_basis_review: 'Проверка правовых оснований',
  complaint: 'Коллективная жалоба', progress_report: 'Сравнение готовности',
  work_status: 'Остановка / задержка работ', document: 'Документ', screenshot: 'Скриншот',
}

function EvidenceForm({ complexId, onSaved, onCancel }: { complexId: string; onSaved: () => void; onCancel: () => void }) {
  const { api } = useAuth()
  const ads = useApiQuery<Page<Advertisement>>(`/api/v1/complexes/${complexId}/advertisements?limit=100`)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setBusy(true); setError(null)
    try {
      if (!form.get('sourceUrl') && !String(form.get('sourceReference')).trim()) throw new Error('Укажите ссылку или реквизиты исходного документа.')
      await api('/api/v1/evidence', { method: 'POST', body: JSON.stringify({
        complexId, type: form.get('type'), advertisementId: form.get('advertisementId') || null,
        sourceUrl: form.get('sourceUrl') || null, sourceReference: form.get('sourceReference'),
        excerpt: form.get('excerpt'), capturedAt: new Date(String(form.get('capturedAt'))).toISOString(),
      }) })
      onSaved()
    } catch (error) { setError(errorMessage(error)) } finally { setBusy(false) }
  }
  return <form className="editor-form" onSubmit={submit}><EditorHeading>Добавить доказательство</EditorHeading>
    <p className="form-hint">Новая запись будет иметь статус «Нет подтверждения». Проверка и решение по фактору — отдельные действия.</p>
    <FormField label="Тип источника"><select name="type" defaultValue="document">{Object.entries(evidenceTypes).filter(([key]) => key !== 'screenshot').map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></FormField>
    <FormField label="Связанное объявление"><select name="advertisementId" defaultValue="" disabled={ads.loading || Boolean(ads.error)}><option value="">Не связано с объявлением</option>{ads.data?.items.map((ad) => <option key={ad.id} value={ad.id}>{ad.account} · {ad.text.slice(0, 55)}</option>)}</select></FormField>
    {ads.error && <ErrorState message={ads.error} retry={ads.refresh} />}
    {ads.data?.nextCursor && <p className="form-hint">Показаны первые 100 объявлений по объекту.</p>}
    <FormField label="Ссылка на источник"><input name="sourceUrl" type="url" placeholder="https://…" /></FormField>
    <FormField label="Реквизиты документа / источник"><input name="sourceReference" maxLength={2000} placeholder="Номер, дата, автор документа" /></FormField>
    <FormField label="Точная цитата / выдержка"><textarea name="excerpt" required rows={4} maxLength={20000} /></FormField>
    <FormField label="Дата фиксации" hint="Местное время вашего компьютера."><input name="capturedAt" type="datetime-local" required /></FormField>
    {error && <ErrorState message={error} />}
    <div className="form-actions"><Button disabled={busy}>Сохранить источник</Button><Button variant="outline" type="button" onClick={onCancel} disabled={busy}>Отмена</Button></div>
  </form>
}

export function EvidenceReviewForm({ item, onSaved, onCancel }: { item: Evidence; onSaved: () => void; onCancel: () => void }) {
  const { api } = useAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [decision, setDecision] = useState<'confirmed' | 'rejected'>('confirmed')
  const booleanFields: [keyof Evidence, string][] = item.type === 'legal_basis_review'
    ? [['applicableBasesChecked', 'Проверены все применимые правовые основания, включая гарантию'], ['legalAbsenceVerified', 'Документально установлено отсутствие применимых оснований']]
    : ['advertisement', 'screenshot'].includes(item.type)
      ? [['paymentOfferVerified', 'Источник содержит прямое предложение внести платёж'], ['activeAdvertisingVerified', 'Активная реклама проверена'], ['constructionVerified', 'Жильё ещё находится на стадии строительства']]
      : item.type === 'complaint' ? [['collectiveComplaintVerified', 'Подтверждена коллективная жалоба о привлечении средств']]
        : item.type === 'work_status' ? [['workStoppageVerified', 'Подтверждена существенная остановка / задержка работ']] : []
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setBusy(true); setError(null)
    try {
      const payload: Record<string, unknown> = { decision: form.get('decision'), notes: form.get('notes'), expectedVersion: item.version }
      for (const [field] of booleanFields) payload[field] = form.get(field) === 'on'
      if (item.type === 'progress_report') {
        for (const field of ['claimedPercent', 'verifiedPercent']) payload[field] = form.get(field) === '' ? null : Number(form.get(field))
        for (const field of ['claimedAt', 'verifiedAt']) payload[field] = form.get(field) ? new Date(String(form.get(field))).toISOString() : null
        for (const field of ['claimedSource', 'verifiedSource']) payload[field] = form.get(field)
      }
      await api(`/api/v1/evidence/${item.id}/decision`, { method: 'POST', body: JSON.stringify(payload) })
      onSaved()
    } catch (error) { setError(errorMessage(error)) } finally { setBusy(false) }
  }
  return <form className="editor-form review-form" onSubmit={submit} aria-busy={busy}><EditorHeading>Проверка источника</EditorHeading>
    {item.type === 'legal_basis_review' && <p className="inline-notice">Отсутствие записи в реестре или отдельного разрешения не доказывает R1. Нужна документальная проверка применимых оснований.</p>}
    {booleanFields.map(([field, label]) => <label className="checkbox-field" key={field}><input type="checkbox" name={field} disabled={busy} defaultChecked={Boolean(item[field])} /><span>{label}</span></label>)}
    {item.type === 'progress_report' && <div className="form-grid">
      <FormField label="Заявленная готовность, %"><input name="claimedPercent" type="number" min={0} max={100} defaultValue={item.claimedPercent ?? ''} required={decision === 'confirmed'} /></FormField>
      <FormField label="Проверенная готовность, %"><input name="verifiedPercent" type="number" min={0} max={100} defaultValue={item.verifiedPercent ?? ''} required={decision === 'confirmed'} /></FormField>
      <FormField label="Дата заявления"><input name="claimedAt" type="datetime-local" defaultValue={localDateTime(item.claimedAt)} required={decision === 'confirmed'} /></FormField><FormField label="Дата проверки"><input name="verifiedAt" type="datetime-local" defaultValue={localDateTime(item.verifiedAt)} required={decision === 'confirmed'} /></FormField>
      <FormField label="Источник заявления"><input name="claimedSource" defaultValue={item.claimedSource} required={decision === 'confirmed'} /></FormField><FormField label="Источник проверки"><input name="verifiedSource" defaultValue={item.verifiedSource} required={decision === 'confirmed'} /></FormField>
    </div>}
    <FormField label="Результат проверки"><select name="decision" value={decision} disabled={busy} onChange={(event) => setDecision(event.target.value as 'confirmed' | 'rejected')}><option value="confirmed">Подтвердить источник и отмеченные факты</option><option value="rejected">Отклонить источник</option></select></FormField>
    <FormField label="Обоснование решения"><textarea name="notes" required disabled={busy} maxLength={5000} rows={3} /></FormField>
    <p className="form-hint">Это действие ещё не подтверждает фактор риска. Решение по фактору принимается в панели R1–R6.</p>
    {error && <ErrorState message={error} />}
    <div className="form-actions"><Button disabled={busy}>{busy ? 'Сохраняем проверку…' : 'Сохранить проверку'}</Button><Button type="button" variant="outline" onClick={onCancel} disabled={busy}>Отмена</Button></div>
  </form>
}

export function EvidencePanel({ complex_, onChanged }: { complex_: Complex; onChanged: () => void }) {
  const [params] = useSearchParams()
  const sourceId = params.get('source')
  const source = useApiQuery<Evidence>(sourceId ? `/api/v1/evidence/${encodeURIComponent(sourceId)}` : null)
  const [creating, setCreating] = useState(false)
  const [reviewId, setReviewId] = useState<string | null>(null)
  const [cursor, setCursor] = useState('')
  const { data, loading, error, refresh } = useApiQuery<Page<Evidence>>(`/api/v1/complexes/${complex_.id}/evidence?limit=50${cursor ? `&cursor=${cursor}` : ''}`)
  const selected = source.data?.complexId === complex_.id ? source.data : null
  const items = selected ? [selected, ...(data?.items || []).filter((item) => item.id !== selected.id)] : data?.items || []
  const selectedNotice = useRef<HTMLParagraphElement>(null)
  useEffect(() => {
    if (!loading && sourceId && selected?.id === sourceId) {
      selectedNotice.current?.focus({ preventScroll: true })
      selectedNotice.current?.scrollIntoView?.({ block: 'start' })
    }
  }, [sourceId, selected?.id, loading])
  return <>
    <div className="panel-heading"><div><h2>Источники и доказательства</h2><p>Оригинал → проверка аналитика → решение по фактору</p></div><Button variant="outline" onClick={() => setCreating(true)}>Добавить источник</Button></div>
    {creating && <EvidenceForm complexId={complex_.id} onCancel={() => setCreating(false)} onSaved={() => { setCreating(false); setCursor(''); refresh() }} />}
    {source.error && <ErrorState message={source.error} retry={source.refresh} />}
    {loading ? <LoadingState /> : error ? <ErrorState message={error} retry={refresh} />
      : !items.length ? <EmptyState title="Источники ещё не добавлены" />
      : <div className="evidence-list">{items.map((item) => {
        const locked = complex_.factors.some((factor) => factor.status === 'confirmed' && factor.evidenceIds.includes(item.id))
        return <article className="evidence-card" key={item.id} id={`evidence-${item.id}`}>
          {item.id === sourceId && <p className="inline-notice" ref={selectedNotice} tabIndex={-1}>Источник, выбранный по ссылке</p>}
          <div className="flex flex-wrap items-center justify-between gap-2"><strong>{evidenceTypes[item.type]}</strong><StatusBadge status={item.status} label={{ confirmed: 'Источник проверен', unknown: 'Источник не проверен', proposed: 'Требует проверки источника', rejected: 'Источник отклонён' }[item.status]} /></div>
          <blockquote>{item.excerpt}</blockquote><EvidenceProvenance reference={item.sourceReference} /><SourceLink url={item.sourceUrl} />
          <p className="mt-3 text-xs text-muted-foreground">Зафиксировано {formatDate(item.capturedAt)}{item.reviewer && ` · Проверил ${item.reviewer}, ${formatDate(item.reviewedAt)}`}</p>
          {item.sha256 && <p className="mt-2 break-all text-xs text-muted-foreground">SHA-256: {item.sha256}</p>}
          {item.storagePath && <EvidenceFile id={item.id} />}
          {locked ? <p className="mt-3 text-xs text-muted-foreground">Источник поддерживает подтверждённый фактор. Для повторной проверки сначала пересмотрите фактор.</p>
            : <><Button className="mt-4" variant="outline" size="sm" id={`review-trigger-${item.id}`} aria-expanded={reviewId === item.id} aria-controls={reviewId === item.id ? `review-${item.id}` : undefined} onClick={() => setReviewId(item.id)}>{item.status === 'confirmed' ? 'Пересмотреть проверку источника' : 'Проверить источник'}</Button>{item.status === 'confirmed' && <p className="form-hint mt-3">Источник проверен. Чтобы учесть факт в баллах, отдельно откройте «Решение по фактору» в панели R1–R6.</p>}</>}
          {reviewId === item.id && <div id={`review-${item.id}`}><EvidenceReviewForm item={item} onCancel={() => { document.getElementById(`review-trigger-${item.id}`)?.focus(); setReviewId(null) }} onSaved={() => { setReviewId(null); refresh(); source.refresh(); onChanged() }} /></div>}
        </article>
      })}</div>}
    {(cursor || data?.nextCursor) && <div className="pagination"><Button variant="outline" onClick={() => setCursor('')}>В начало</Button>{data?.nextCursor && <Button variant="outline" onClick={() => setCursor(data.nextCursor!)}>Далее</Button>}</div>}
  </>
}

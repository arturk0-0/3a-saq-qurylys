import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { EditorHeading, ErrorState, FormField, LoadingState, ReviewGuide } from '@/components/WorkspaceUI'
import { useAuth } from '@/features/auth/AuthProvider'
import { errorMessage, factorLabels, formatDate } from '@/lib/labels'
import { useApiQuery } from '@/lib/useApiQuery'
import type { Advertisement, Page } from '@/lib/types'
import { EvidenceFile } from '@/features/complexes/EvidenceFile'
import { MatchingCandidates } from './MatchingCandidates'

interface Hypothesis { id: string; code: 'R2' | 'R3'; quote: string; explanation: string; confidence: number | null;
  status: 'proposed' | 'accepted' | 'rejected'; evidenceId: string; model: string; reviewer: string | null; version: number }
interface AnalysisRun { id: string; status: 'running' | 'succeeded' | 'failed'; createdAt: string; model: string;
  errorCode?: string; extraction?: { uncertainty: string; mentionedComplexes: string[]; paymentTerms: string[]; hypotheses: unknown[] } }

export function AnalysisPanel({ adId }: { adId: string }) {
  const { api } = useAuth()
  const ad = useApiQuery<Advertisement>(`/api/v1/advertisements/${adId}`)
  const [cursor, setCursor] = useState('')
  const hypotheses = useApiQuery<Page<Hypothesis>>(`/api/v1/advertisements/${adId}/hypotheses?limit=50${cursor ? `&cursor=${cursor}` : ''}`)
  const runs = useApiQuery<Page<AnalysisRun>>(`/api/v1/advertisements/${adId}/analysis?limit=100`)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [imageId, setImageId] = useState('')
  const [reviewId, setReviewId] = useState<string | null>(null)
  async function analyze() {
    if (!ad.data) return
    setBusy(true); setError(null)
    try {
      await api(`/api/v1/advertisements/${adId}/analyze`, { method: 'POST', body: JSON.stringify({ requestId: crypto.randomUUID(), expectedVersion: ad.data.version, screenshotId: imageId || null }) })
      setCursor(''); hypotheses.refresh(); runs.refresh()
    } catch (error) { setError(errorMessage(error)); runs.refresh() } finally { setBusy(false) }
  }
  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!ad.data) return
    const file = new FormData(event.currentTarget).get('image') as File
    if (!file?.size) return
    if (file.size > 6 * 1024 * 1024) { setError('Максимальный размер — 6 МБ.'); return }
    setBusy(true); setError(null)
    try {
      const saved = await api<{ id: string }>(`/api/v1/advertisements/${adId}/screenshots?expected_version=${ad.data.version}`, { method: 'POST', headers: { 'Content-Type': file.type }, body: file })
      setImageId(saved.id); ad.refresh()
    } catch (error) { setError(errorMessage(error)) } finally { setBusy(false) }
  }
  async function review(event: FormEvent<HTMLFormElement>, hypothesis: Hypothesis) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setBusy(true); setError(null)
    try {
      await api(`/api/v1/hypotheses/${hypothesis.id}/decision`, { method: 'POST', body: JSON.stringify({ decision: form.get('decision'), notes: form.get('notes'), expectedVersion: hypothesis.version }) })
      setReviewId(null); hypotheses.refresh()
    } catch (error) { setError(errorMessage(error)) } finally { setBusy(false) }
  }
  return <section className="analysis-panel mt-5 border-t border-border pt-5" aria-label="Анализ объявления">
    <h3 className="font-semibold">AI-гипотезы · Gemini</h3>
    <p className="form-hint">AI предлагает цитаты для проверки. Он не устанавливает отсутствие разрешений и не подтверждает факторы риска.</p>
    <ReviewGuide />
    {ad.loading ? <LoadingState /> : ad.error ? <ErrorState message={ad.error} retry={ad.refresh} /> : <>
      <form className="editor-form" onSubmit={upload}><FormField label="Добавить скриншот" hint="JPEG, PNG или WebP, до 6 МБ. Оригинал хранится приватно."><input name="image" type="file" accept="image/jpeg,image/png,image/webp" required disabled={busy} /></FormField><Button variant="outline" disabled={busy}>Загрузить</Button></form>
      <FormField label="Источник анализа"><select value={imageId} disabled={busy} onChange={(event) => setImageId(event.target.value)}><option value="">Текст объявления</option>{ad.data?.attachmentIds.map((id, index) => <option value={id} key={id}>Скриншот {index + 1}</option>)}</select></FormField>
      {imageId && <EvidenceFile key={imageId} id={imageId} />}
      <Button className="my-3" disabled={busy} onClick={analyze}>{busy ? 'Выполняется…' : 'Анализировать выбранный источник'}</Button>
    </>}
    {error && <ErrorState message={error} />}
    {runs.error && <ErrorState message={runs.error} retry={runs.refresh} />}
    {runs.data?.items.slice().sort((a, b) => b.createdAt.localeCompare(a.createdAt)).map((run) => <details className="my-3 text-sm" key={run.id}><summary>{formatDate(run.createdAt)} · {run.model} · {{ running: 'Запрос начат — обновите результат', failed: 'Анализ не выполнен', succeeded: 'Анализ завершён' }[run.status]}</summary>
      {run.extraction && <div className="inline-notice"><p>{run.extraction.uncertainty}</p><p>Названия из источника: {run.extraction.mentionedComplexes.join(', ') || 'не найдены'}. Привязку к ЖК выбирает аналитик.</p><p>Условия оплаты: {run.extraction.paymentTerms.join('; ') || 'не выделены'}.</p>{!run.extraction.hypotheses.length && <p>Поддержанных гипотез нет. Это не подтверждение безопасности объекта.</p>}</div>}
      {run.status === 'succeeded' && Boolean(run.extraction?.mentionedComplexes.length) && <MatchingCandidates adId={adId} runId={run.id} />}
      {run.status === 'failed' && <p>Результат не сохранён как гипотеза. Код: {run.errorCode}</p>}</details>)}
    {runs.data?.nextCursor && <p className="form-hint">Показаны первые 100 запусков по ID. Полная история доступна в журнале ЖК.</p>}
    <Button size="sm" variant="outline" disabled={busy} onClick={() => { runs.refresh(); hypotheses.refresh(); ad.refresh() }}>Обновить результаты</Button>
    {hypotheses.loading ? <LoadingState /> : hypotheses.error ? <ErrorState message={hypotheses.error} retry={hypotheses.refresh} /> : hypotheses.data?.items.map((item) => <article className="evidence-card mt-4" key={item.id}>
      <strong>{item.code} · {factorLabels[item.code]}</strong><p className="text-sm">{{ proposed: 'AI-гипотеза — не подтверждено', accepted: 'Принято для проверки доказательства', rejected: 'Гипотеза отклонена' }[item.status]}</p>
      <blockquote>{item.quote}</blockquote><p>{item.explanation}</p><p className="form-hint">Модель: {item.model}. {item.confidence !== null && `Самооценка модели: ${Math.round(item.confidence * 100)}% (не вероятность нарушения).`}</p>
      {item.status === 'proposed' && <Button size="sm" variant="outline" onClick={() => setReviewId(item.id)}>Рассмотреть гипотезу</Button>}
      {reviewId === item.id && <form className="editor-form" onSubmit={(event) => review(event, item)}><EditorHeading>Рассмотрение гипотезы {item.code}</EditorHeading><FormField label="Решение по гипотезе"><select name="decision"><option value="accepted">Принять к проверке</option><option value="rejected">Отклонить</option></select></FormField><FormField label="Обоснование"><textarea name="notes" required maxLength={2000} /></FormField><div className="form-actions"><Button disabled={busy}>Сохранить решение</Button><Button type="button" variant="outline" disabled={busy} onClick={() => setReviewId(null)}>Отмена</Button></div></form>}
      {item.status === 'accepted' && <p className="inline-notice">Далее откройте ЖК → Доказательства, проверьте источник и отдельно подтвердите фактор в панели R1–R6. Балл пока не изменён.</p>}
      <Link className="detail-link mt-3" to={`/complexes/${ad.data?.complexId}?tab=evidence&source=${item.evidenceId}`}>К доказательству →</Link>
    </article>)}
    {(cursor || hypotheses.data?.nextCursor) && <div className="pagination"><Button variant="outline" onClick={() => setCursor('')}>В начало</Button>{hypotheses.data?.nextCursor && <Button variant="outline" onClick={() => setCursor(hypotheses.data!.nextCursor!)}>Далее</Button>}</div>}
  </section>
}

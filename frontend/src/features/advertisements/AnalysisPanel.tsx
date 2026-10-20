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
  const [activity, setActivity] = useState<'upload' | 'review' | null>(null)
  const busy = activity !== null
  const [error, setError] = useState<string | null>(null)
  const [imageId, setImageId] = useState('')
  const [uploadedName, setUploadedName] = useState('')
  const [reviewId, setReviewId] = useState<string | null>(null)
  const [reviewNotes, setReviewNotes] = useState('')
  const [reviewDecision, setReviewDecision] = useState('accepted')
  const latestRun = runs.data?.items.slice().sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0]
  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!ad.data) return
    const file = new FormData(event.currentTarget).get('image') as File
    if (!file?.size) return
    if (file.size > 6 * 1024 * 1024) { setError('Максимальный размер — 6 МБ.'); return }
    setActivity('upload'); setError(null)
    try {
      const saved = await api<{ id: string }>(`/api/v1/advertisements/${adId}/screenshots?expected_version=${ad.data.version}`, { method: 'POST', headers: { 'Content-Type': file.type }, body: file })
      setImageId(saved.id); setUploadedName(file.name); ad.refresh()
    } catch (error) { setError(errorMessage(error)) } finally { setActivity(null) }
  }
  async function review(event: FormEvent<HTMLFormElement>, hypothesis: Hypothesis) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setActivity('review'); setError(null)
    try {
      await api(`/api/v1/hypotheses/${hypothesis.id}/decision`, { method: 'POST', body: JSON.stringify({ decision: form.get('decision'), notes: form.get('notes'), expectedVersion: hypothesis.version }) })
      setReviewId(null); setReviewNotes(''); hypotheses.refresh()
    } catch (error) { setError(errorMessage(error)) } finally { setActivity(null) }
  }
  return <section className="analysis-panel" aria-label="Анализ объявления" aria-busy={busy}>
    <h3 className="analysis-title">Проверка объявления с AI</h3>
    <p className="form-hint">AI предлагает цитаты для проверки. Он не устанавливает отсутствие разрешений и не подтверждает факторы риска.</p>
    {ad.loading ? <LoadingState /> : ad.error ? <ErrorState message={ad.error} retry={ad.refresh} /> : <>
      <div className="analysis-step">
        <div className="step-heading"><span className="step-number">1</span><div><h4>Сохранённые оригиналы</h4><p>Выберите текст или скриншот для просмотра.</p></div></div>
        <FormField label="Сохранённый материал"><select value={imageId} disabled={busy} onChange={(event) => setImageId(event.target.value)}><option value="">Текст объявления</option>{ad.data?.attachmentIds.map((id, index) => <option value={id} key={id}>Скриншот {index + 1}</option>)}</select></FormField>
        <form className="screenshot-upload" onSubmit={upload}>
          <FormField label="Добавить скриншот" hint="JPEG, PNG или WebP, до 6 МБ. После загрузки скриншот выбирается автоматически."><input name="image" type="file" accept="image/jpeg,image/png,image/webp" required disabled={busy} /></FormField>
          <Button variant="outline" disabled={busy}>{activity === 'upload' ? 'Загружаем…' : 'Загрузить'}</Button>
        </form>
        {uploadedName && <p className="upload-success" role="status">Загружен файл «{uploadedName}». Выбран для просмотра {imageId ? 'скриншот' : 'текст объявления'}.</p>}
        {imageId && <EvidenceFile key={imageId} id={imageId} />}
      </div>
      <div className="analysis-step analysis-launch">
        <div className="step-heading"><span className="step-number">2</span><div><h4>Автоматический анализ</h4><p>Поддерживаемые новые материалы поступают в очередь. Проверка выбранных гипотез сохраняется в разделе «Реклама».</p></div></div>
        <p className="selected-source">Просматриваемый оригинал: <strong>{imageId ? `Скриншот ${Math.max(0, ad.data?.attachmentIds.indexOf(imageId) ?? -1) + 1}` : 'Текст объявления'}</strong></p>
        <Link className="detail-link" to={`/advertising?complexId=${encodeURIComponent(ad.data?.complexId || '')}`}>Перейти к единой проверке →</Link>
      </div>
    </>}
    {error && <ErrorState message={error} />}
    {latestRun && <p className="analysis-run-status" role="status">Последний запуск: <strong>{{ running: 'Выполняется — обновите результаты', failed: 'Анализ не выполнен', succeeded: 'Анализ завершён' }[latestRun.status]}</strong> · {formatDate(latestRun.createdAt)}</p>}
    {runs.error && <ErrorState message={runs.error} retry={runs.refresh} />}
    <details className="analysis-history"><summary>История запусков анализа ({runs.data?.items.length ?? 0})</summary>
    {runs.data?.items.slice().sort((a, b) => b.createdAt.localeCompare(a.createdAt)).map((run) => <details className="my-3 text-sm" key={run.id}><summary>{formatDate(run.createdAt)} · {run.model} · {{ running: 'Запрос начат — обновите результат', failed: 'Анализ не выполнен', succeeded: 'Анализ завершён' }[run.status]}</summary>
      {run.extraction && <div className="inline-notice"><p>{run.extraction.uncertainty}</p><p>Названия из источника: {run.extraction.mentionedComplexes.join(', ') || 'не найдены'}. Привязку к ЖК выбирает аналитик.</p><p>Условия оплаты: {run.extraction.paymentTerms.join('; ') || 'не выделены'}.</p>{!run.extraction.hypotheses.length && <p>Поддержанных гипотез нет. Это не подтверждение безопасности объекта.</p>}</div>}
      {run.status === 'succeeded' && Boolean(run.extraction?.mentionedComplexes.length) && <MatchingCandidates adId={adId} runId={run.id} />}
      {run.status === 'failed' && <p>Результат не сохранён как гипотеза. Код: {run.errorCode}</p>}</details>)}
    {runs.data?.nextCursor && <p className="form-hint">Показаны первые 100 запусков по ID. Полная история доступна в журнале ЖК.</p>}
    </details>
    <div className="results-heading"><div className="step-heading"><span className="step-number">3</span><div><h4>Рассмотрите гипотезы</h4><p>В списке — результаты разных запусков. Проверяйте цитату по оригиналу.</p></div></div>
    <Button size="sm" variant="outline" disabled={busy} onClick={() => { setError(null); runs.refresh(); hypotheses.refresh(); ad.refresh() }}>Обновить результаты</Button></div>
    <details className="review-help"><summary>Как гипотеза влияет на оценку?</summary><ReviewGuide /></details>
    {!hypotheses.loading && !hypotheses.error && !hypotheses.data?.items.length && <p className="inline-notice">Гипотез пока нет. Статус автоматического анализа доступен в разделе «Реклама».</p>}
    {hypotheses.loading ? <LoadingState /> : hypotheses.error ? <ErrorState message={hypotheses.error} retry={hypotheses.refresh} /> : hypotheses.data?.items.map((item) => <article className={`evidence-card hypothesis-card hypothesis-${item.status}`} key={item.id}>
      <h4 className="hypothesis-title">{item.code} · {factorLabels[item.code]}</h4><p className={`hypothesis-status hypothesis-status-${item.status}`}>{{ proposed: 'AI-гипотеза — не подтверждено', accepted: 'Принято для проверки доказательства', rejected: 'Гипотеза отклонена' }[item.status]}</p>
      <blockquote>{item.quote}</blockquote><p>{item.explanation}</p><details className="model-details"><summary>Сведения об AI-анализе</summary><p className="form-hint">Модель: {item.model}. {item.confidence !== null && `Самооценка модели: ${Math.round(item.confidence * 100)}% (не вероятность нарушения).`}</p></details>
      {item.status === 'proposed' && <Button className="hypothesis-review-action" size="sm" disabled={busy} onClick={() => { if (reviewId !== item.id) { setReviewNotes(''); setReviewDecision('accepted') }; setReviewId(item.id) }}>Рассмотреть гипотезу</Button>}
      {reviewId === item.id && (item.status === 'proposed'
        ? <form className="editor-form" onSubmit={(event) => review(event, item)}><EditorHeading>Рассмотрение гипотезы {item.code}</EditorHeading><p className="form-hint">Принять — передать цитату на проверку источника. Подтверждение фактора и изменение баллов выполняются отдельно в карточке ЖК.</p><FormField label="Решение по гипотезе"><select name="decision" disabled={busy} value={reviewDecision} onChange={event => setReviewDecision(event.target.value)}><option value="accepted">Принять к проверке</option><option value="rejected">Отклонить</option></select></FormField><FormField label="Обоснование"><textarea name="notes" required maxLength={2000} disabled={busy} value={reviewNotes} onChange={event => setReviewNotes(event.target.value)} /></FormField><div className="form-actions"><Button disabled={busy}>Сохранить решение</Button><Button type="button" variant="outline" disabled={busy} onClick={() => setReviewId(null)}>Отмена</Button></div></form>
        : <p className="inline-notice">Гипотеза уже рассмотрена. Несохранённый текст вашего решения: {reviewNotes || 'не введён'}. Повторное решение не отправлено.</p>)}
      {item.status === 'accepted' && <p className="inline-notice">Далее откройте ЖК → Доказательства, проверьте источник и отдельно подтвердите фактор в панели R1–R6. Балл пока не изменён.</p>}
      <Link className="detail-link evidence-next-link" to={`/complexes/${ad.data?.complexId}?tab=evidence&source=${item.evidenceId}`}>К доказательству →</Link>
    </article>)}
    {(cursor || hypotheses.data?.nextCursor) && <div className="pagination"><Button variant="outline" onClick={() => setCursor('')}>В начало</Button>{hypotheses.data?.nextCursor && <Button variant="outline" onClick={() => setCursor(hypotheses.data!.nextCursor!)}>Далее</Button>}</div>}
  </section>
}

import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { ActorName } from '@/components/ActorName'
import { EmptyState, ErrorState, FormField, LoadingState, PageHeading } from '@/components/WorkspaceUI'
import { useAuth } from '@/features/auth/AuthProvider'
import { errorMessage, formatDate } from '@/lib/labels'
import { useApiQuery } from '@/lib/useApiQuery'
import { reviewLabels, safeReference, statusLabels, validPhoto, visibilityLabels, type DroneRun, type Inspection, type Review } from './types'
import './drone.css'

function Results({ run }: { run: DroneRun }) {
  if (!run.result) return <p>{run.status === 'running' ? 'Анализ ещё выполняется.' : 'Анализ не завершён. Снимок сохранён.'}</p>
  return <><p className="drone-summary">{run.result.summary}</p><div className="drone-observations">{run.result.observations.map(observation => {
    const criterion = run.checklist.find(c => c.id === observation.criterionId)
    const source = criterion?.sourceUrl ? safeReference(criterion.sourceUrl) : null
    return <article key={observation.criterionId} className={'drone-observation observation-' + observation.visibility}>
      <span className="drone-state">{visibilityLabels[observation.visibility]}</span><h3>{criterion?.label || 'Пункт чек-листа'}</h3><p>{observation.explanation}</p>
      {source && <a href={source} target="_blank" rel="noopener noreferrer" className="source-link">Источник критерия ↗</a>}
    </article>
  })}</div><div className="drone-limitations"><strong>Ограничения снимка</strong><p>{run.result.limitations}</p><p>«Не видно в кадре» не означает, что объект отсутствует на площадке. Наблюдения ИИ требуют проверки экспертом и не подтверждают соблюдение или нарушение строительных норм.</p></div></>
}

function Photo({ item }: { item: Inspection }) {
  const { api } = useAuth()
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    if (!item.photo) return
    let active = true, objectUrl: string | null = null
    const controller = new AbortController()
    setError(null); setUrl(null)
    api<Blob>('/api/v1/drone-inspections/' + item.id + '/photo', { signal: controller.signal }).then(blob => {
      if (active) { objectUrl = URL.createObjectURL(blob); setUrl(objectUrl) }
    }).catch(failure => { if (active) setError(errorMessage(failure)) })
    return () => { active = false; controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [api, item.id, item.photo?.id, retry])
  if (error) return <ErrorState message={error} retry={() => setRetry(n => n + 1)} />
  if (!url) return <LoadingState />
  return <><img className="drone-original" src={url} alt={'Снимок: ' + item.title} /><a className="detail-link" href={url} download={'drone-' + item.id + '.' + item.photo!.mediaType.split('/')[1]}>Скачать оригинал ↓</a></>
}

export function DroneDetail() {
  const { id } = useParams()
  const { state } = useLocation()
  const { api } = useAuth()
  const path = '/api/v1/drone-inspections/' + encodeURIComponent(id ?? '')
  const query = useApiQuery<Inspection>(id ? path : null)
  const [updated, setUpdated] = useState<Inspection | null>(null)
  const [cursor, setCursor] = useState('')
  const history = useApiQuery<{ items: DroneRun[]; nextCursor: string | null }>(id && query.data ? path + '/runs?limit=20' + (cursor ? '&cursor=' + cursor : '') : null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>((state as { uploadError?: string } | null)?.uploadError ?? null)
  const [file, setFile] = useState<File | null>(null)
  const [decision, setDecision] = useState<Review['decision']>('needs_followup')
  const [notes, setNotes] = useState('')
  const pending = useRef<{ id: string; version: number } | null>(null)
  const item = updated ?? query.data
  async function reload() {
    try { setUpdated(await api<Inspection>(path)); history.refresh() }
    catch (failure) { setError(errorMessage(failure)) }
  }
  async function action(kind: 'photo' | 'analyze' | 'review', event?: FormEvent) {
    event?.preventDefault(); if (!item) return
    setError(null)
    if (kind === 'photo' && (!file || !validPhoto(file))) { setError('Выберите JPEG, PNG или WebP до 6 МБ.'); return }
    setBusy(true)
    try {
      let result: Inspection
      if (kind === 'photo') result = await api<Inspection>(path + '/photo?expected_version=' + item.version, { method: 'POST', body: file!, headers: { 'Content-Type': file!.type } })
      else if (kind === 'analyze') {
        if (!pending.current || pending.current.version !== item.version) pending.current = { id: crypto.randomUUID(), version: item.version }
        result = await api<Inspection>(path + '/analyze', { method: 'POST', body: JSON.stringify({ expectedVersion: pending.current.version, requestId: pending.current.id }) })
      } else result = await api<Inspection>(path + '/review', { method: 'POST', body: JSON.stringify({ expectedVersion: item.version, runId: item.latestRunId, decision, notes: notes.trim() }) })
      setUpdated(result); history.refresh(); setCursor('')
      if (kind === 'review') setNotes('')
    } catch (failure) {
      setError(errorMessage(failure))
      // Read-only reconciliation after timeout/409; never automatically repeat an AI call.
      try { setUpdated(await api<Inspection>(path)); history.refresh() } catch { /* Keep the saved view and form. */ }
    } finally { setBusy(false) }
  }
  if (query.loading && !item) return <LoadingState />
  if (query.error && !item) return <ErrorState message={query.error} retry={query.refresh} />
  if (!item) return <EmptyState title="Инспекция не найдена" />
  const currentReview = item.reviews.filter(review => review.runId === item.latestRunId).at(-1)
  return <div className="drone-feature"><Link to="/drone-inspections" className="back-link">← К дрон-инспекциям</Link>
    <PageHeading eyebrow="Осмотр по фотографии" title={item.title} description={item.complexName || 'Без привязки к ЖК'} action={<Button variant="outline" disabled={busy} onClick={() => void reload()}>Обновить результаты</Button>} />
    <div className="drone-context"><span className={'drone-state state-' + item.status}>{statusLabels[item.status]}</span><p>{item.complexId && <Link to={'/complexes/' + item.complexId}>Карточка ЖК → · </Link>}Съёмка: {item.capturedAt ? formatDate(item.capturedAt) + ' — указано пользователем' : 'время не указано'} · Загружено: {item.photo ? formatDate(item.photo.uploadedAt) : 'фотография ещё не добавлена'}</p></div>
    {error && <ErrorState message={error} />}
    <div className="drone-detail-grid"><section className="panel"><h2>Оригинал снимка</h2>{item.photo ? <Photo item={item} /> : <form onSubmit={event => void action('photo', event)}><FormField label="Фотография с дрона" hint="Статичный JPEG, PNG или WebP до 6 МБ."><input type="file" required disabled={busy} accept="image/jpeg,image/png,image/webp" onChange={e => setFile(e.target.files?.[0] ?? null)} /></FormField><Button disabled={busy}>Загрузить фотографию</Button></form>}
      <details className="drone-file-details"><summary>Данные снимка и чек-лист</summary>{item.photo && <><p>Размер: {(item.photo.sizeBytes / 1024 / 1024).toFixed(2)} МБ · {item.photo.mediaType}</p><p>SHA-256: <span className="drone-hash">{item.photo.sha256}</span></p></>}<ol>{item.checklist.map(c => <li key={c.id}>{c.label}{c.sourceUrl && safeReference(c.sourceUrl) && <> · <a href={safeReference(c.sourceUrl)!} target="_blank" rel="noopener noreferrer">Указанный источник ↗</a></>}</li>)}</ol><p>Чек-лист и фото сохраняются вместе с каждым анализом. Ссылки на нормы не загружаются и автоматически не проверяются.</p></details>
    </section><section className="panel"><div className="drone-result-heading"><h2>Наблюдения ИИ</h2>{item.photo && <Button disabled={busy || !item.canAnalyze} onClick={() => void action('analyze')}>{busy ? 'Выполняем действие…' : item.latestRun ? 'Проанализировать заново' : 'Анализировать фотографию'}</Button>}</div>
      {item.latestRun ? <Results run={item.latestRun} /> : <p>Анализ ещё не запускался. После загрузки нажмите «Анализировать фотографию».</p>}
      {item.latestRun?.status === 'running' && <p className="inline-notice" role="status">Сервер обрабатывает снимок. Обновите результаты перед новым запуском. Для прерванного анализа повтор станет доступен через пять минут.</p>}
      {item.latestRun?.status === 'failed' && <p className="inline-notice">Оригинал сохранён. Проверьте сообщение об ошибке или повторите анализ позже.</p>}
      {!item.canAnalyze && item.analysisCount >= 20 && <p>Достигнут предел анализов этой инспекции. Для другого снимка создайте новую запись.</p>}
      <p className="form-hint">Этот осмотр хранится отдельно и не изменяет рекламный риск ЖК.</p>
    </section></div>
    {item.latestRun?.status === 'succeeded' && <section className="panel"><h2>Решение эксперта</h2>{currentReview && <div role="status" className="drone-current-review"><strong>{reviewLabels[currentReview.decision]}</strong><p>{currentReview.notes}</p><p><ActorName uid={currentReview.reviewer} /> · {formatDate(currentReview.reviewedAt)}</p></div>}
      <form onSubmit={event => void action('review', event)}><fieldset disabled={busy} className="drone-fields"><FormField label="Результат рассмотрения"><select value={decision} onChange={e => setDecision(e.target.value as Review['decision'])}>{Object.entries(reviewLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></FormField><FormField label="Комментарий эксперта"><textarea required maxLength={2000} rows={3} value={notes} onChange={e => setNotes(e.target.value)} /></FormField><Button disabled={!notes.trim()}>Сохранить решение</Button></fieldset></form>
    </section>}
    <section className="panel"><h2>История решений</h2>{!item.reviews.length ? <p>Решений пока нет.</p> : [...item.reviews].reverse().map((review, index) => <article className="drone-review-row" key={review.reviewedAt + index}><strong>{reviewLabels[review.decision]}</strong><p>{review.notes}</p><p><ActorName uid={review.reviewer} /> · {formatDate(review.reviewedAt)}{review.runId !== item.latestRunId && ' · предыдущий анализ'}</p></article>)}</section>
    <section className="panel"><details><summary>История анализов</summary>{history.loading ? <LoadingState /> : history.error ? <ErrorState message={history.error} retry={history.refresh} /> : history.data?.items.length ? history.data.items.map(run => <article key={run.id} className="drone-review-row"><h3>{formatDate(run.createdAt)} · {run.status === 'succeeded' ? 'Анализ завершён' : run.status === 'running' ? 'Выполняется' : 'Не завершён'}{run.id === item.latestRunId ? ' · текущий' : ''}</h3><details><summary>Показать наблюдения</summary><Results run={run} /></details></article>) : <p>Предыдущих анализов пока нет.</p>}
      {(cursor || history.data?.nextCursor) && <div className="form-actions"><Button variant="outline" onClick={() => setCursor('')}>В начало</Button>{history.data?.nextCursor && <Button variant="outline" onClick={() => setCursor(history.data!.nextCursor!)}>Ещё анализы</Button>}</div>}</details></section>
  </div>
}

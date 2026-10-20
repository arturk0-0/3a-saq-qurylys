import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { ErrorState, FormField } from '@/components/WorkspaceUI'
import { EvidenceFile } from '@/features/complexes/EvidenceFile'
import { useAuth } from '@/features/auth/AuthProvider'
import { errorMessage, formatDate } from '@/lib/labels'
import { safeExternal } from './presentation'
import type { MaterialDetail, MaterialPage, Occurrence } from './types'

export function Originals({ detail, requestedId, requestSequence = 0, onRecords }: {
  detail: MaterialDetail; requestedId: string | null; requestSequence?: number; onRecords: (records: Occurrence[]) => void
}) {
  const { api } = useAuth()
  const [records, setRecords] = useState(detail.occurrences)
  const [cursor, setCursor] = useState(detail.nextOccurrenceCursor)
  const [selected, setSelected] = useState(detail.occurrences[0]?.id || '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [originalError, setOriginalError] = useState<string | null>(null)
  const [originalBusy, setOriginalBusy] = useState(false)
  const [originalAttempt, setOriginalAttempt] = useState(0)
  const controller = useRef<AbortController | null>(null)
  const original = useRef<HTMLElement>(null)
  useEffect(() => () => controller.current?.abort(), [])
  useEffect(() => { onRecords(records) }, [records, onRecords])
  useEffect(() => {
    if (requestedId && records.some(record => record.id === requestedId)) {
      setSelected(requestedId); original.current?.focus({ preventScroll: true }); original.current?.scrollIntoView?.({ block: 'nearest' })
    }
  }, [requestedId, records, requestSequence])
  useEffect(() => {
    setOriginalError(null)
    if (!requestedId || records.some(record => record.id === requestedId)) { setOriginalBusy(false); return }
    const request = new AbortController()
    setOriginalBusy(true); setOriginalError(null)
    void api<Occurrence>(`/api/v1/materials/${encodeURIComponent(detail.id)}/occurrences/${encodeURIComponent(requestedId)}`, { signal: request.signal })
      .then(record => { if (!request.signal.aborted) setRecords(previous => previous.some(item => item.id === record.id) ? previous : [...previous, record]) })
      .catch(failure => { if (!request.signal.aborted) setOriginalError(errorMessage(failure)) })
      .finally(() => { if (!request.signal.aborted) setOriginalBusy(false) })
    return () => request.abort()
  }, [api, detail.id, requestedId, records, originalAttempt])
  async function more() {
    if (!cursor || busy) return
    const request = new AbortController(); controller.current = request
    setBusy(true); setError(null)
    try {
      const page = await api<MaterialPage<Occurrence>>(`/api/v1/materials/${encodeURIComponent(detail.id)}/occurrences?limit=20&cursor=${encodeURIComponent(cursor)}`, { signal: request.signal })
      if (request.signal.aborted) return
      setRecords(previous => [...previous, ...page.items.filter(item => !previous.some(record => record.id === item.id))])
      setCursor(page.nextCursor)
    } catch (failure) { if (!request.signal.aborted) setError(errorMessage(failure)) } finally { if (!request.signal.aborted) setBusy(false) }
  }
  const current = records.find(record => record.id === selected) || records[0]
  const url = safeExternal(current?.originalUrl || null)
  return <section className="panel content-pad ad-panel ad-stack" ref={original} tabIndex={-1} aria-label="Оригиналы материала">
    <h2>Оригиналы и публикации</h2>
    <p>Зарегистрировано публикаций: {detail.occurrenceCount}. Здесь загружено: {records.length}.</p>
    <FormField label="Публикация"><select value={current?.id || ''} onChange={event => setSelected(event.target.value)}>{records.map(record => <option key={record.id} value={record.id}>{record.platform} · {record.account} · {formatDate(record.publishedAt)}</option>)}</select></FormField>
    {originalBusy && <p role="status">Загружаем оригинал выбранной цитаты…</p>}
    {originalError && <ErrorState message={originalError} retry={() => setOriginalAttempt(value => value + 1)} />}
    {requestedId && !records.some(record => record.id === requestedId) && <p role="status">Оригинал этой цитаты ещё не загружен. Подтверждать без проверки оригинала нельзя.</p>}
    {!current ? <p>Оригиналы пока недоступны. Это не подтверждение фактов.</p> : <>
      <div className="ad-meta"><span>{current.platform}</span><span>{current.account}</span><span>{current.origin === 'manual' ? 'Добавлено вручную' : 'Получено автоматически'}</span></div>
      <p className="form-hint">Опубликовано: {formatDate(current.publishedAt)} · Зафиксировано: {formatDate(current.capturedAt)}</p>
      {url ? <a className="detail-link" href={url} target="_blank" rel="noopener noreferrer">Открыть исходную публикацию ↗</a> : <p>Без доступной внешней ссылки. Сверьте сохранённый оригинал.</p>}
      <p className="ad-original">{current.text || 'Текст оригинала недоступен.'}</p>
      <div className="ad-media">{current.media.map(media => <section className="ad-hypothesis" key={media.id}>
        <strong>{media.kind === 'video' ? 'Видео' : media.kind === 'thumbnail' ? 'Превью, не полное видео' : 'Изображение'}</strong>
        <p>{media.analyzed ? 'Этот материал отмечен сервером как проанализированный.' : 'Этот материал не анализировался.'}</p>
        {media.availability === 'private' && media.kind !== 'video' ? <EvidenceFile key={media.id} id={media.id} />
          : media.availability === 'external' && safeExternal(media.url) ? <a className="detail-link" href={safeExternal(media.url)!} target="_blank" rel="noopener noreferrer">Открыть внешний материал ↗</a>
          : <p>Файл недоступен для просмотра здесь. Не считайте его проверенным.</p>}
      </section>)}</div>
    </>}
    {error && <ErrorState message={error} retry={() => void more()} />}
    {cursor && <Button variant="outline" disabled={busy} onClick={() => void more()}>{busy ? 'Загружаем публикации…' : 'Следующие публикации'}</Button>}
  </section>
}

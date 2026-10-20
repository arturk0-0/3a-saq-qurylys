import { RegistryPanel } from './RegistryPanel'
import { ActorName } from '@/components/ActorName'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { ErrorState, FormField, LoadingState, SourceLink } from '@/components/WorkspaceUI'
import { useAuth } from '@/features/auth/AuthProvider'
import { useApiQuery } from '@/lib/useApiQuery'
import { errorMessage, factorLabels, formatDate } from '@/lib/labels'
import type { Complex } from '@/lib/types'
import { findingLabels, safeMonitorError, contentLabel, type Finding, type Page } from './types'

interface History { id: string; action: string; actorUid: string; createdAt: string; details: { notes?: string; decision?: string } }
export function FindingDetail({ id, liveRegistry, changed }: { id: string; liveRegistry: boolean; changed: () => void }) {
  const { api } = useAuth()
  const query = useApiQuery<Finding>('/api/v1/monitoring/items/' + id)
  const [historyCursor, setHistoryCursor] = useState('')
  const history = useApiQuery<Page<History>>('/api/v1/monitoring/items/' + id + '/history?limit=10' + (historyCursor ? '&cursor=' + historyCursor : ''))
  const complexes = useApiQuery<Page<Complex>>(liveRegistry ? '/api/v1/complexes?limit=100&sort=name' : null)
  const [decision, setDecision] = useState<'investigating' | 'dismissed' | 'new'>('investigating')
  const [notes, setNotes] = useState('')
  const [complexId, setComplexId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const item = query.data
  function refresh() { query.refresh(); history.refresh(); changed() }
  async function operation(action: 'review' | 'attach', event?: FormEvent) {
    event?.preventDefault()
    if (!item) return
    setBusy(true); setError(null); setNotice(null)
    try {
      const body = action === 'review' ? { expectedVersion: item.version, decision, notes }
        : { expectedVersion: item.version, complexId, notes }
      await api('/api/v1/monitoring/items/' + id + '/' + action, { method: 'POST', body: JSON.stringify(body) })
      setNotice(action === 'review' ? 'Решение по находке сохранено. Оценка R1–R6 не менялась.' : 'Публикация передана в карточку ЖК. Факторы требуют отдельного подтверждения.')
      refresh()
    } catch (failure) { setError(errorMessage(failure)) } finally { setBusy(false) }
  }
  return <section className="panel monitor-detail" aria-label="Проверка находки">
    <div className="monitor-heading"><h2>Проверка находки</h2><Button variant="outline" disabled={busy} onClick={refresh}>Обновить материал</Button></div>
    {error && <ErrorState message={error} />}
    {notice && <p role="status" className="inline-notice">{notice}</p>}
    {query.loading ? <LoadingState /> : query.error ? <ErrorState message={query.error} retry={query.refresh} /> : item && <>
      <div className="monitor-heading"><span className="monitor-tag">{findingLabels[item.status]}</span><strong>{item.contentKind === 'search_snippet' ? 'Поисковый фрагмент — требуется оригинал' : contentLabel(item.contentKind)}</strong></div>
      <h3>{item.title || item.account}</h3>
      <SourceLink url={item.originalUrl} />
      <p>Опубликовано: {formatDate(item.publishedAt)} · Получено: {formatDate(item.createdAt)}</p>
      {item.contentKind === 'instagram_ad' && <div className="monitor-meta-info"><p>Библиотека Meta · ID {item.adArchiveId} · {item.adActive ? 'Активно при получении' : 'Статус требует проверки'}</p><p>Начало рекламного показа: {formatDate(item.adStartedAt)}. Это не дата публикации исходного поста.</p><p>Платформы по данным поставщика: {item.platforms?.join(', ')}</p></div>}
      <blockquote className="monitor-original">{item.text}</blockquote>
      {Boolean(item.media?.length) && <details className="monitor-section"><summary>Рекламные материалы · {item.media!.length}</summary><p>Материалы открываются на сайте источника. AI в этой карточке анализирует только текст.</p><ul className="monitor-media">{item.media!.map((m, i) => <li key={m.kind + i}><a className="detail-link" href={m.url} target="_blank" rel="noopener noreferrer">{m.kind === 'video' ? 'Видео' : m.kind === 'thumbnail' ? 'Превью' : 'Изображение'} {i + 1} ↗</a></li>)}</ul></details>}
      <details className="monitor-section"><summary>Почему материал попал в очередь</summary>      <p className="inline-notice">Это находка для проверки, не установленное нарушение. Сверьте регион, рекламу, актуальность и правовое основание.</p>
      <div className="monitor-reasons"><div><strong>Слова о регионе</strong><p>{item.regionMatches.join(', ')}</p></div><div><strong>Слова о жилье</strong><p>{item.housingMatches.join(', ')}</p></div><div><strong>Слова об оплате</strong><p>{item.paymentMatches.join(', ') || 'В тексте не найдены'}</p></div></div>
      </details>
      <details><summary>Происхождение и контрольные суммы</summary><p>Ссылка обнаружения: {item.discoveryUrl}</p><p>Текст: {item.textSha256}</p><p>Ответ источника: {item.responseSha256}</p><p>Группа ревизий: {item.revisionKey}</p><p>Последнее обнаружение: {formatDate(item.lastSeenAt)} · источников: {item.sourceIds.length}</p></details>
      <RegistryPanel item={item} disabled={busy} saved={() => { setNotice('Правовое основание сохранено. Находка убрана из активной очереди; документ и история доступны в «Все находки». Баллы R1–R6 не менялись.'); refresh() }} />
      <section className="monitor-section"><h3>AI-гипотезы</h3>
        {item.aiStatus === 'not_requested' && <p>Выделите возможные признаки риска в тексте объявления.</p>}
        {item.aiStatus === 'running' && <p role="status">Gemini обрабатывает материал. Обновите результат перед повторной попыткой.</p>}
        {item.aiStatus === 'failed' && <p className="inline-notice">{safeMonitorError(item.aiError)} Оригинал сохранён. Перед повтором проверьте результат в истории.</p>}
        {item.extraction && <><p className="form-hint">Модель: {item.aiModel}. Все выводы ниже — неподтверждённые гипотезы.</p>
          {item.extraction.hypotheses.length === 0 && <p>AI не выделил R2/R3 в этом материале. Это не проверка законности.</p>}
          {item.extraction.hypotheses.map((h, i) => <article className="evidence-card" key={i}><h4>{h.code} · {factorLabels[h.code]}</h4><blockquote>{h.quote}</blockquote><p>{h.explanation}</p></article>)}
          <p>{item.extraction.uncertainty}</p></>}
        {!item.advertisementId && <Link className="detail-link" to="/advertising">Проверить материал в разделе «Реклама» →</Link>}
      </section>
      {item.reviewer && <p className="inline-notice">Решение: {findingLabels[item.status]}. {item.notes}<br />Эксперт: <ActorName uid={item.reviewer} /> · {formatDate(item.reviewedAt)}</p>}
      <form className="editor-form monitor-section" onSubmit={e => void operation('review', e)}>
        <h3>Решение эксперта по находке</h3>
        <FormField label="Решение по находке"><select value={decision} disabled={busy} onChange={e => setDecision(e.target.value as typeof decision)}><option value="investigating">Взять в работу</option><option value="dismissed">Отложить / не относится к проверке</option><option value="new">Вернуть в очередь</option></select></FormField>
        <FormField label="Обоснование решения"><textarea required maxLength={2000} rows={4} value={notes} disabled={busy} onChange={e => setNotes(e.target.value)} /></FormField>
        <Button disabled={busy || !notes.trim()}>Сохранить решение эксперта</Button>
      </form>
      <section className="monitor-section"><h3>Продолжить проверку в реестре ЖК</h3>
        {item.advertisementId ? <Link className="detail-link" to={'/advertisements/' + item.advertisementId}>Открыть сохранённое объявление →</Link>
          : !liveRegistry ? <p>Для продолжения нужна карточка реального ЖК. Пока сохраните решение в этой очереди.</p>
          : <><p>Выберите проверенный реальный ЖК. Сохранится исходный текст и неподтверждённые AI-гипотезы; баллы не изменятся.</p>
            {complexes.error && <ErrorState message={complexes.error} retry={complexes.refresh} />}
            <FormField label="Реальный жилой комплекс"><select value={complexId} disabled={busy || complexes.loading} onChange={e => setComplexId(e.target.value)}><option value="">Выберите объект</option>{complexes.data?.items.filter(c => !c.demo).map(c => <option key={c.id} value={c.id}>{c.name} · {c.city}</option>)}</select></FormField>
            {!complexes.loading && !complexes.data?.items.some(c => !c.demo) && <p>Доступных реальных ЖК нет. Сначала требуется проверенная запись реестра.</p>}
            {complexes.data?.nextCursor && <p>Показаны первые 100 объектов. Не выбирайте похожий объект вместо нужного.</p>}
            <Button variant="outline" disabled={busy || !complexId || !notes.trim() || item.aiStatus === 'running'} onClick={() => void operation('attach')}>Передать в карточку ЖК с обоснованием выше</Button></>}
      </section>
      <details className="monitor-section"><summary>История решений по находке</summary>
        {history.loading ? <LoadingState /> : history.error ? <ErrorState message={history.error} retry={history.refresh} /> : history.data?.items.length ? history.data.items.map(e => <p key={e.id} className="history-entry">{formatDate(e.createdAt)} · <ActorName uid={e.actorUid} /> · {e.action === 'item.basis.confirm' ? 'Проверено правовое основание' : e.action === 'item.review' ? 'Решение эксперта' : e.action === 'item.attach' ? 'Передано в карточку ЖК' : 'Попытка AI-анализа'}<br />{e.details.notes}</p>) : <p>Решений пока нет.</p>}
        {(historyCursor || history.data?.nextCursor) && <div className="form-actions"><Button variant="outline" onClick={() => setHistoryCursor('')}>Начало истории</Button>{history.data?.nextCursor && <Button variant="outline" onClick={() => setHistoryCursor(history.data!.nextCursor!)}>Далее по истории</Button>}</div>}
      </details>
    </>}
  </section>
}

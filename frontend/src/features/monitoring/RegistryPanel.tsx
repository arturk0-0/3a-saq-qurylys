import { useState, type FormEvent } from 'react'
import { ActorName } from '@/components/ActorName'
import { Button } from '@/components/ui/button'
import { ErrorState, FormField, SourceLink } from '@/components/WorkspaceUI'
import { useAuth } from '@/features/auth/AuthProvider'
import { ApiError } from '@/lib/http'
import { errorMessage, formatDate } from '@/lib/labels'
import type { Finding, RegistryDocument, RegistrySearch } from './types'

const checks = {
  objectMatches: 'Название и адрес соответствуют объекту рекламы',
  phaseMatches: 'Разрешение относится к нужной очереди, блоку и этапу строительства',
  holderMatches: 'Застройщик, получатель средств и БИН соответствуют документу',
  documentValidityChecked: 'Проверены оригинал документа, его действие и отсутствие отмены на дату рекламы',
  advertisementDateChecked: 'Дата рекламы проверена по оригиналу, а не по дате начала кампании',
  otherRisksReviewed: 'Других оснований продолжать проверку этой находки после сверки не осталось',
}
function localDate(value: string) {
  const parts = new Intl.DateTimeFormat('en', { timeZone: 'Asia/Qyzylorda', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date(value))
  return ['year', 'month', 'day'].map(key => parts.find(p => p.type === key)?.value).join('-')
}
export function RegistryPanel({ item, disabled, saved }: { item: Finding; disabled: boolean; saved: () => void }) {
  const { api } = useAuth()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<RegistrySearch | null>(null)
  const [document, setDocument] = useState<RegistryDocument | null>(null)
  const [adDate, setAdDate] = useState(item.publishedAt ? localDate(item.publishedAt) : '')
  const [accepted, setAccepted] = useState<Record<string, boolean>>({})
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const locked = busy || disabled || item.aiStatus === 'running' || Boolean(item.advertisementId)
  async function perform(action: 'search' | 'detail' | 'confirm', recordId?: string, event?: FormEvent) {
    event?.preventDefault()
    setBusy(true); setError(null)
    try {
      const base = '/api/v1/monitoring/items/' + item.id
      if (action === 'search') {
        setResults(null); setDocument(null); setAccepted({})
        setResults(await api<RegistrySearch>(base + '/registry?q=' + encodeURIComponent(query.trim())))
      } else if (action === 'detail') {
        setDocument(null); setAccepted({})
        setDocument(await api<RegistryDocument>(base + '/registry/' + recordId))
      } else if (document) {
        await api(base + '/basis-review', { method: 'POST', body: JSON.stringify({
          expectedVersion: item.version, expectedDocumentSha256: document.documentSha256, recordId: document.recordId, advertisementDate: adDate,
          ...accepted, notes,
        }) })
        saved()
      }
    } catch (failure) {
      setError(errorMessage(failure))
      if (failure instanceof ApiError && failure.code === 'REGISTRY_DOCUMENT_CHANGED') { setDocument(null); setAccepted({}) }
    } finally { setBusy(false) }
  }
  return <details className="monitor-section registry-panel"><summary>Сверить разрешение или гарантию</summary>
    {item.basisReview && <div className="inline-notice"><strong>Правовое основание подтверждено экспертом</strong><p>{item.basisReview.document.name} · {item.basisReview.document.reference} от {item.basisReview.document.issuedOn}</p><SourceLink url={item.basisReview.document.sourceUrl} /><p>На дату рекламы {item.basisReview.advertisementDate}. <ActorName uid={item.basisReview.reviewer} /> · {formatDate(item.basisReview.reviewedAt)}</p><p>{item.basisReview.notes}</p></div>}
    <p>Найдите объект по названию ЖК или адресу. Совпадение в каталоге — кандидат для сверки. Разрешение или гарантия не отменяют другие признаки риска.</p>
    <form className="editor-form" onSubmit={e => void perform('search', undefined, e)}>
      <FormField label="Название ЖК или адрес для сверки"><input value={query} required minLength={3} maxLength={100} disabled={busy || disabled} onChange={e => setQuery(e.target.value)} /></FormField>
      <Button variant="outline" disabled={busy || disabled || query.trim().length < 3}>Найти в реестрах</Button>
    </form>
    {error && <ErrorState message={error} />}
    {busy && <p role="status">Проверяем реестр…</p>}
    {results && <><p className="form-hint">Запрошено {formatDate(results.checkedAt)}. Отсутствие совпадений не подтверждает отсутствие разрешения.</p>
      {results.sources.map(source => <section key={source.provider} className="monitor-section"><h3>{source.provider === 'homeportal' ? 'Homeportal · КЖК' : 'Открытые данные · Ashyq Data'}</h3>
        {source.status === 'unavailable' ? <p className="inline-notice">Источник недоступен или изменил формат. Проверьте документ на сайте реестра.</p> : source.candidates.length === 0 ? <p>Совпадений по этому запросу не найдено. Попробуйте другое написание названия или адрес.</p> : source.candidates.map(candidate => <article className="evidence-card" key={candidate.recordId}>
          <h4>{candidate.name}</h4><p>{candidate.address}</p><p>Застройщик: {candidate.developer}{candidate.developerBin && ' · БИН ' + candidate.developerBin}</p><p>Уполномоченная компания: {candidate.holder}{candidate.holderBin && ' · БИН ' + candidate.holderBin}</p>
          {candidate.reference && <p>Реквизиты записи: {candidate.reference}</p>}
          {candidate.dataAsOf && <p>Данные набора на {candidate.dataAsOf}. Актуальность документа требует проверки.</p>}
          <SourceLink url={candidate.sourceUrl} />
          {candidate.provider === 'homeportal' && <Button variant="outline" disabled={busy || disabled} onClick={() => void perform('detail', candidate.recordId)}>Проверить документ</Button>}
        </article>)}
        {source.limited && <p>Показана только часть результатов. Уточните запрос; полный охват не гарантируется.</p>}
      </section>)}
    </>}
    {document && <form className="editor-form monitor-section" onSubmit={e => void perform('confirm', undefined, e)}>
      <h3>{document.kind === 'guarantee' ? 'Гарантия КЖК' : 'Разрешение МИО'} · {document.reference}</h3>
      <p>{document.name} · {document.address}</p><p>Выдано {document.issuedOn}. Застройщик: {document.developer} · БИН {document.developerBin}. Уполномоченная компания: {document.holder} · БИН {document.holderBin}.</p>
      <SourceLink url={document.sourceUrl} /><p>Карточка каталога не подтверждает отсутствие отмены документа. Сверьте оригинал и область его действия. Дата ввода дома не является сроком действия разрешения.</p>
      <FormField label="Проверенная дата рекламы"><input type="date" required value={adDate} max={localDate(item.createdAt)} readOnly={Boolean(item.publishedAt)} disabled={locked} onChange={e => setAdDate(e.target.value)} /></FormField>
      {Object.entries(checks).map(([key, label]) => <label className="registry-check" key={key}><input type="checkbox" required checked={Boolean(accepted[key])} disabled={locked} onChange={e => setAccepted({ ...accepted, [key]: e.target.checked })} /><span>{label}</span></label>)}
      <FormField label="Обоснование сверки документа"><textarea rows={3} required maxLength={2000} value={notes} disabled={locked} onChange={e => setNotes(e.target.value)} /></FormField>
      <p>Решение завершит проверку только этой находки. Исходник и история сохранятся. Факторы R1–R6 не изменятся.</p>
      {item.advertisementId && <p>Находка уже передана в карточку ЖК. Проверьте правовое основание в этой карточке.</p>}
      <Button disabled={locked || !adDate || !notes.trim() || !Object.keys(checks).every(k => accepted[k])}>Основание проверено — завершить проверку</Button>
    </form>}
    <p><a className="detail-link" href="https://elicense.kz/LicensingContent/SimpleSearchLicense" target="_blank" rel="noopener noreferrer">Проверить оригинал в E-License ↗</a></p>
  </details>
}

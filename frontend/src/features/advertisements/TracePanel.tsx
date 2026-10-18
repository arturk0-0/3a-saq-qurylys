import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { EditorHeading, ErrorState, FormField, LoadingState, SourceLink } from '@/components/WorkspaceUI'
import { useAuth } from '@/features/auth/AuthProvider'
import { errorMessage, formatDate } from '@/lib/labels'
import { useApiQuery } from '@/lib/useApiQuery'

interface Match { kind: 'phone' | 'domain' | 'alias'; normalized: string; left: { quote: string }[]; right: { quote: string }[] }
interface Snapshot { leftId: string; rightId: string; leftVersion: number; rightVersion: number; matches: Match[]; nameOnly: boolean }
interface SavedLink { id: string; version: number; status: 'proposed' | 'confirmed' | 'rejected'; reviewer: string | null; reviewedAt: string | null; notes: string }
interface Candidate { id: string; snapshot: Snapshot; otherAdvertisement: { id: string; complexId: string; platform: string; account: string; sourceUrl: string }; saved: SavedLink | null }
interface Result { items: Candidate[]; scannedCount: number; scanLimited: boolean; resultsLimited: boolean; identifiersLimited: boolean }
const kindLabels = { phone: 'Общий номер телефона', domain: 'Общий домен сайта', alias: 'Совпадение названия' }

export function TracePanel({ adId }: { adId: string }) {
  const { api } = useAuth()
  const query = useApiQuery<Result>(`/api/v1/advertisements/${adId}/trace`)
  const [selected, setSelected] = useState<string | null>(null)
  const [decision, setDecision] = useState('confirmed')
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState<Record<string, SavedLink>>({})
  function refresh() { setError(null); setSaved({}); query.refresh() }
  async function submit(event: FormEvent<HTMLFormElement>, item: Candidate) {
    event.preventDefault(); setBusy(true); setError(null)
    try {
      let record = saved[item.id] || item.saved
      if (!record) {
        const s = item.snapshot
        record = await api<SavedLink>(`/api/v1/advertisements/${adId}/trace`, { method: 'POST', body: JSON.stringify({
          otherAdvertisementId: item.otherAdvertisement.id, expectedSnapshotId: item.id,
          expectedVersion: s.leftId === adId ? s.leftVersion : s.rightVersion,
          expectedOtherVersion: s.leftId === adId ? s.rightVersion : s.leftVersion,
        }) })
        const proposed = record
        setSaved(prev => ({ ...prev, [item.id]: proposed }))
      }
      if (record.status !== 'proposed') { query.refresh(); return }
      const reviewed = await api<SavedLink>(`/api/v1/ad-links/${record.id}/decision`, { method: 'POST', body: JSON.stringify({ decision, notes, expectedVersion: record.version }) })
      setSaved(prev => ({ ...prev, [item.id]: reviewed })); setSelected(null); setNotes('')
    } catch (failure) { setError(errorMessage(failure)) } finally { setBusy(false) }
  }
  return <section className="trace-panel" aria-label="Рекламный след" aria-busy={busy}>
    <div className="panel-heading"><div><h3>Рекламный след</h3><p className="form-hint">Телефоны, WhatsApp, сайты и названия в текстах сохранённых объявлений.</p></div><Button size="sm" variant="outline" disabled={busy} onClick={refresh}>Обновить совпадения</Button></div>
    <p className="inline-notice">Совпадение не доказывает общего владельца или нарушение. Решение здесь относится только к совпадению; баллы R1–R6 не меняются.</p>
    {error && <ErrorState message={error} />}
    {query.loading ? <LoadingState /> : query.error ? <ErrorState message={query.error} retry={refresh} /> : <>
      <p className="form-hint">Проверено других объявлений: {query.data?.scannedCount ?? 0}. Изображения и закрытые аккаунты не сравниваются.</p>
      {(query.data?.scanLimited || query.data?.resultsLimited || query.data?.identifiersLimited) && <p className="inline-notice">Показана ограниченная выборка: до 199 других объявлений, 20 совпадений и 100 фрагментов на текст. Отсутствие совпадения не означает отсутствия связи.</p>}
      {!query.data?.items.length && <p className="trace-empty">В проверенной выборке совпадений не найдено.</p>}
      {selected && !query.data?.items.some(item => item.id === selected) && <p className="inline-notice">Материалы изменились. Несохранённое обоснование: {notes || 'не введено'}. Выберите актуальное совпадение для новой проверки.</p>}
      {query.data?.items.map(item => {
        const record = saved[item.id] || item.saved
        const isLeft = item.snapshot.leftId === adId
        return <article className="evidence-card trace-card" key={item.id}>
          <div className="trace-card-heading"><h4>{item.otherAdvertisement.platform} · @{item.otherAdvertisement.account}</h4><span className={`trace-status trace-status-${record?.status || 'proposed'}`}>{{ proposed: 'Подсказка — требует проверки', confirmed: 'Совпадение подтверждено', rejected: 'Совпадение отклонено' }[record?.status || 'proposed']}</span></div>
          {item.snapshot.nameOnly && <p className="form-hint">Совпало только название — слабая подсказка. Общий контакт не найден.</p>}
          {item.snapshot.matches.map((match, index) => <div className="trace-match" key={index}><strong>{kindLabels[match.kind]}: {match.normalized}</strong><div className="trace-quotes"><div><span>Это объявление</span><blockquote>{(isLeft ? match.left : match.right)[0].quote}</blockquote></div><div><span>Другое объявление</span><blockquote>{(isLeft ? match.right : match.left)[0].quote}</blockquote></div></div></div>)}
          <div className="form-actions"><Link className="detail-link" to={`/advertisements/${item.otherAdvertisement.id}`}>К связанному объявлению →</Link><SourceLink url={item.otherAdvertisement.sourceUrl} /></div>
          {record?.reviewer && <div className="trace-review-result"><p>Проверил {record.reviewer} · {formatDate(record.reviewedAt)}</p><p>{record.notes}</p></div>}
          {(!record || record.status === 'proposed') && <Button className="mt-4" size="sm" id={`trace-trigger-${adId}-${item.id}`} aria-expanded={selected === item.id} aria-controls={selected === item.id ? `trace-review-${adId}-${item.id}` : undefined} disabled={busy} onClick={() => { if (selected !== item.id) { setNotes(''); setDecision('confirmed') }; setSelected(item.id) }}>Рассмотреть совпадение</Button>}
          {selected === item.id && ((!record || record.status === 'proposed') ? <form className="editor-form" id={`trace-review-${adId}-${item.id}`} onSubmit={event => submit(event, item)}>
            <EditorHeading>Проверка совпадения</EditorHeading><p className="form-hint">Сверьте оба оригинала. Подтверждайте только совпадение контакта или названия; это не вывод об общем владельце.</p>
            <FormField label="Решение по совпадению"><select value={decision} disabled={busy} onChange={event => setDecision(event.target.value)}><option value="confirmed">Подтвердить совпадение</option><option value="rejected">Отклонить совпадение</option></select></FormField>
            <FormField label="Обоснование совпадения"><textarea required maxLength={2000} value={notes} disabled={busy} onChange={event => setNotes(event.target.value)} /></FormField>
            <div className="form-actions"><Button disabled={busy}>{busy ? 'Сохраняем…' : 'Сохранить решение о совпадении'}</Button><Button type="button" variant="outline" disabled={busy} onClick={() => { document.getElementById(`trace-trigger-${adId}-${item.id}`)?.focus(); setSelected(null) }}>Отмена</Button></div>
          </form> : <p className="inline-notice">Совпадение уже рассмотрено. Несохранённое обоснование: {notes || 'не введено'}. Повторное решение не отправлено.</p>)}
        </article>
      })}
    </>}
  </section>
}

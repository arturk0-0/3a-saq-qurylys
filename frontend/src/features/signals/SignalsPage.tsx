import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { DemoBadge, EmptyState, ErrorState, EvidenceProvenance, FormField, LoadingState, PageHeading, RiskBadge, ScrollableTable, SourceLink } from '@/components/WorkspaceUI'
import { useAuth } from '@/features/auth/AuthProvider'
import { errorMessage, factorLabels, formatDate, statusLabels } from '@/lib/labels'
import { useApiQuery } from '@/lib/useApiQuery'
import type { AuditEvent, Complex, Evidence, Page, RiskResult } from '@/lib/types'

type SignalStatus = 'draft' | 'pending_review' | 'confirmed' | 'returned'
const labels: Record<SignalStatus, string> = { draft: 'Черновик', pending_review: 'На проверке', confirmed: 'Подтверждён аналитиком', returned: 'Возвращён' }
interface SignalSummary { id: string; complexId: string; complexName: string; title: string; reason: string; status: SignalStatus; risk: RiskResult; createdAt: string; version: number }
interface Signal extends Omit<SignalSummary, 'risk' | 'complexName'> {
  snapshot: { complex: Complex; developer: { name: string; bin: string }; risk: RiskResult; evidence: (Evidence & { excerptTruncated: boolean })[]; capturedAt: string }
  createdBy: string; reviewer: string | null; reviewedAt: string | null; reviewNotes: string
}

export function CreateSignal() {
  const [params] = useSearchParams()
  const id = params.get('complex') || ''
  const complex_ = useApiQuery<Complex>(id ? `/api/v1/complexes/${encodeURIComponent(id)}` : null)
  const { api } = useAuth()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!complex_.data) return
    const form = new FormData(event.currentTarget)
    setBusy(true); setError(null)
    try {
      const signal = await api<Signal>('/api/v1/signals', { method: 'POST', body: JSON.stringify({ complexId: id, expectedComplexVersion: complex_.data.version, title: form.get('title'), reason: form.get('reason') }) })
      navigate(`/signals/${signal.id}`)
    } catch (error) { setError(errorMessage(error)) } finally { setBusy(false) }
  }
  if (!id) return <EmptyState title="Выберите ЖК"><Link to="/complexes">Открыть реестр</Link></EmptyState>
  if (complex_.loading) return <LoadingState />
  if (complex_.error) return <ErrorState message={complex_.error} retry={complex_.refresh} />
  return <><PageHeading eyebrow="Решение аналитика" title="Новый сигнал" description={complex_.data?.name || ''} />
    <section className="panel"><form className="editor-form" onSubmit={submit}><RiskBadge risk={complex_.data!.risk} />
      <FormField label="Заголовок сигнала"><input name="title" required maxLength={500} defaultValue={`DEMO — проверка ${complex_.data?.name.replace(/^DEMO — /, '')}`} /></FormField>
      <FormField label="Основание для проверки"><textarea name="reason" rows={4} required maxLength={2000} /></FormField>
      <p className="inline-notice">Будет создан черновик со снимком текущих проверенных данных. Подтверждение сигнала — отдельное действие. В органы ничего не отправляется.</p>
      {error && <ErrorState message={error} />}<Button disabled={busy}>Создать черновик</Button></form></section></>
}

export function SignalsPage() {
  const [status, setStatus] = useState('')
  const [cursor, setCursor] = useState('')
  const { data, loading, error, refresh } = useApiQuery<Page<SignalSummary>>(`/api/v1/signals?limit=50${status ? `&status=${status}` : ''}${cursor ? `&cursor=${cursor}` : ''}`)
  return <><PageHeading eyebrow="Проверка и отчётность" title="Сигналы" description="Снимки проверенных данных и отдельные решения аналитиков." />
    <section className="panel"><div className="filter-bar"><select aria-label="Статус сигнала" value={status} onChange={(event) => { setStatus(event.target.value); setCursor('') }}><option value="">Все статусы</option>{Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><Link className="detail-link" to="/complexes">Создать сигнал из карточки ЖК →</Link></div>
      {loading ? <LoadingState /> : error ? <ErrorState message={error} retry={refresh} /> : !data?.items.length ? <EmptyState title="Сигналов пока нет"><p>Проверьте факторы в карточке ЖК и создайте черновик.</p></EmptyState>
        : <ScrollableTable label="Сигналы"><table className="data-table"><thead><tr><th>Сигнал / объект</th><th>Статус</th><th>Снимок риска</th><th>Создан</th></tr></thead><tbody>{data.items.map((signal) => <tr key={signal.id}><td><Link className="detail-link" to={`/signals/${signal.id}`}>{signal.title}</Link><span>{signal.complexName}</span></td><td>{labels[signal.status]}</td><td><RiskBadge risk={signal.risk} /></td><td>{formatDate(signal.createdAt)}</td></tr>)}</tbody></table></ScrollableTable>}
      {(cursor || data?.nextCursor) && <div className="pagination"><Button variant="outline" onClick={() => setCursor('')}>В начало</Button>{data?.nextCursor && <Button variant="outline" onClick={() => setCursor(data.nextCursor!)}>Далее</Button>}</div>}</section></>
}

export function SignalDetail() {
  const { id } = useParams()
  const { api } = useAuth()
  const { data: signal, loading, error, refresh } = useApiQuery<Signal>(id ? `/api/v1/signals/${id}` : null)
  const [historyCursor, setHistoryCursor] = useState('')
  const history = useApiQuery<Page<AuditEvent>>(id ? `/api/v1/signals/${id}/history?limit=50${historyCursor ? `&cursor=${historyCursor}` : ''}` : null)
  const current = useApiQuery<Complex>(signal ? `/api/v1/complexes/${signal.complexId}` : null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [decisionNotes, setDecisionNotes] = useState('')
  const [downloading, setDownloading] = useState(false)
  useEffect(() => { setDecisionNotes(''); setActionError(null); setHistoryCursor('') }, [id])
  async function decision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!signal) return
    const form = new FormData(event.currentTarget)
    setBusy(true); setActionError(null)
    try {
      if (form.get('action') === 'confirm' && (current.loading || current.error || !current.data || current.data.version !== signal.snapshot.complex.version)) throw new Error('Перед подтверждением проверьте актуальную карточку ЖК. Обновите данные; текст решения сохранён.')
      await api(`/api/v1/signals/${id}/decision`, { method: 'POST', body: JSON.stringify({ action: form.get('action'), expectedVersion: signal.version, notes: form.get('notes') }) })
      setDecisionNotes('')
      refresh(); history.refresh(); current.refresh()
    } catch (error) { setActionError(errorMessage(error)) } finally { setBusy(false) }
  }
  async function download() {
    setBusy(true); setDownloading(true); setActionError(null)
    try {
      const url = URL.createObjectURL(await api<Blob>(`/api/v1/signals/${id}/report`))
      const anchor = document.createElement('a')
      anchor.href = url; anchor.download = `saq-signal-${id}.pdf`; anchor.hidden = true
      document.body.append(anchor); anchor.click(); anchor.remove()
      setTimeout(() => URL.revokeObjectURL(url), 10000)
    } catch (error) { setActionError(errorMessage(error)) } finally { setBusy(false); setDownloading(false) }
  }
  if (loading) return <LoadingState />
  if (error) return <ErrorState message={error} retry={refresh} />
  if (!signal) return <EmptyState title="Сигнал не найден" />
  const snapshot = signal.snapshot
  const stale = current.data && current.data.version !== snapshot.complex.version
  return <><Link to="/signals" className="back-link">← Все сигналы</Link><PageHeading eyebrow={`Сигнал · версия ${signal.version}`} title={signal.title} description={labels[signal.status]} action={<DemoBadge />} />
    <section className="panel content-pad"><div className="flex flex-wrap items-center justify-between gap-4"><div><h2>{snapshot.complex.name}</h2><Link className="detail-link" to={`/complexes/${signal.complexId}`}>Текущая карточка ЖК →</Link></div><RiskBadge risk={snapshot.risk} /></div>
      <p className="my-4">{signal.reason}</p><p className="form-hint">Снимок версии ЖК {snapshot.complex.version} от {formatDate(snapshot.capturedAt)}. Последующие изменения карточки не меняют этот документ.</p>
      {stale && <p className="inline-notice">Карточка ЖК изменена. Для подтверждения верните сигнал и повторно передайте на проверку: будет сохранён новый снимок.</p>}
      {current.error && <ErrorState message={`Не удалось проверить актуальность карточки ЖК. ${current.error}`} retry={current.refresh} />}
      <ScrollableTable label="Факторы риска сигнала"><table className="data-table"><thead><tr><th>Фактор</th><th>Статус</th><th>Баллы</th><th>Источники</th></tr></thead><tbody>{snapshot.risk.factors.map((factor) => <tr key={factor.code}><td>{factor.code} · {factorLabels[factor.code]}</td><td>{statusLabels[factor.status]}</td><td>{factor.points}</td><td>{factor.evidenceIds.map((eid) => <a className="detail-link block" key={eid} href={`#source-${eid}`}>{eid}</a>)}</td></tr>)}</tbody></table></ScrollableTable>
      <h2 className="mt-6">Проверенные источники</h2>{!snapshot.evidence.length && <p className="form-hint">В снимке нет подтверждённых источников.</p>}{snapshot.evidence.map((item) => <article className="evidence-card" id={`source-${item.id}`} key={item.id}><strong>{item.id}</strong><blockquote>{item.excerpt}{item.excerptTruncated && ' [выдержка сокращена]'}</blockquote><EvidenceProvenance reference={item.sourceReference} /><SourceLink url={item.sourceUrl} /><p className="form-hint">{item.reviewer} · {formatDate(item.reviewedAt)}</p></article>)}
      <p className="mt-4 text-sm">Создал: {signal.createdBy} · {formatDate(signal.createdAt)}</p>
      {signal.reviewer && <p className="text-sm">Проверил: {signal.reviewer} · {formatDate(signal.reviewedAt)}</p>}
      {signal.reviewNotes && <blockquote className="my-3">{signal.reviewNotes}</blockquote>}
      {signal.status !== 'confirmed' && <form className="editor-form" onSubmit={decision} aria-busy={busy}>
        <FormField label="Действие по сигналу"><select name="action" disabled={busy} defaultValue={signal.status === 'pending_review' ? 'return' : 'submit'} key={signal.status}>{signal.status === 'pending_review' ? <><option value="return">Вернуть на доработку</option><option value="confirm" disabled={Boolean(stale) || current.loading || Boolean(current.error) || !current.data}>Подтвердить сигнал</option></> : <option value="submit">Передать на проверку с актуальным снимком</option>}</select></FormField>
        <FormField label="Обоснование решения"><textarea name="notes" required disabled={busy} maxLength={2000} rows={3} value={decisionNotes} onChange={event => setDecisionNotes(event.target.value)} /></FormField>
        <p className="form-hint">Это решение по сигналу. Оно не меняет решения по факторам и не отправляет данные в органы.</p><Button disabled={busy}>Сохранить решение по сигналу</Button>
      </form>}
      {actionError && <ErrorState message={actionError} />}
      <div className="form-actions mt-5 print:hidden"><Button disabled={busy} onClick={download}>{downloading ? 'Готовим PDF…' : 'Скачать PDF'}</Button><Button variant="outline" onClick={() => window.print()}>Печать карточки</Button><Button variant="outline" disabled={busy} onClick={() => { refresh(); history.refresh(); current.refresh() }}>Обновить</Button></div>
      <p className="page-footnote">DEMO: вымышленные данные. Приоритет проверки не является выводом о незаконности.</p></section>
    <section className="panel content-pad mt-6"><h2>История сигнала</h2>{history.loading ? <LoadingState /> : history.error ? <ErrorState message={history.error} retry={history.refresh} /> : !history.data?.items.length ? <p className="form-hint">События истории пока не найдены.</p> : history.data.items.map((event) => <p key={event.id} className="my-3 text-sm">{formatDate(event.createdAt)} · {event.actorUid} · {typeof event.details.to === 'string' ? labels[event.details.to as SignalStatus] : 'Создание'}<br />{String(event.details.notes || '')}</p>)}
      {(historyCursor || history.data?.nextCursor) && <div className="pagination"><Button variant="outline" onClick={() => setHistoryCursor('')}>В начало</Button>{history.data?.nextCursor && <Button variant="outline" onClick={() => setHistoryCursor(history.data!.nextCursor!)}>Далее</Button>}</div>}</section>
  </>
}

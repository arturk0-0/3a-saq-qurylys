import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { ErrorState, FormField, LoadingState, PageHeading, RiskBadge } from '@/components/WorkspaceUI'
import { useAuth } from '@/features/auth/AuthProvider'
import { TracePanel } from '@/features/advertisements/TracePanel'
import { PublicSources } from '@/features/complexes/PublicSources'
import { ApiError } from '@/lib/http'
import { basisLabels, errorMessage, factorLabels, formatDate, statusLabels } from '@/lib/labels'
import type { Complex } from '@/lib/types'
import { AnalysisView, PriorityView } from './presentation'
import { ComplexPicker } from './ComplexPicker'
import { Originals } from './Originals'
import { useResource } from './useResource'
import { ScreenshotUpload } from './ScreenshotUpload'
import { MaterialHistory } from './MaterialHistory'
import type { Decision, MaterialDetail, Occurrence, ReviewBody } from './types'
import './advertising.css'

function ReviewEditor({ detail, materialLoading, refresh, apply }: {
  detail: MaterialDetail; materialLoading: boolean; refresh: () => Promise<MaterialDetail | null>; apply: (value: MaterialDetail) => void
}) {
  const { api } = useAuth()
  const [complexId, setComplexId] = useState(detail.complex?.id || '')
  const complex = useResource<Complex>(complexId ? `/api/v1/complexes/${encodeURIComponent(complexId)}` : null)
  const [decisions, setDecisions] = useState<Record<string, Decision | 'pending'>>({})
  const [notes, setNotes] = useState(detail.review?.notes || '')
  const [disposition, setDisposition] = useState<ReviewBody['disposition']>('reviewed')
  const [requested, setRequested] = useState<string | null>(null)
  const [records, setRecords] = useState<Occurrence[]>(detail.occurrences)
  const [busy, setBusy] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [conflict, setConflict] = useState(false)
  const [refreshed, setRefreshed] = useState(false)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [traceOpen, setTraceOpen] = useState(false)
  const [acknowledged, setAcknowledged] = useState(`${detail.version}:${detail.revisionId}`)
  const request = useRef<{ serialized: string; id: string } | null>(null)
  const analysisRequest = useRef<{ version: number; id: string } | null>(null)
  const token = `${detail.version}:${detail.revisionId}`
  const stale = acknowledged !== token
  useEffect(() => {
    if (!dirty && !conflict) {
      setAcknowledged(token); setComplexId(detail.complex?.id || '')
      setNotes(detail.review?.notes || ''); setDecisions({})
    }
  }, [token, dirty, conflict, detail.complex?.id, detail.review?.notes])
  useEffect(() => { setRecords(detail.occurrences) }, [detail.version, detail.revisionId, detail.occurrences])
  useEffect(() => {
    if (dirty || busy || !['queued', 'running'].includes(detail.analysis.status)) return
    const timer = window.setInterval(() => { if (document.visibilityState === 'visible') void refresh().catch(() => {}) }, 10000)
    return () => window.clearInterval(timer)
  }, [detail.analysis.status, dirty, busy, refresh])
  function changed() { setDirty(true); setSuccess(null); setError(null) }
  function chooseComplex(id: string) {
    if (id === complexId) return
    setComplexId(id)
    setDecisions(Object.fromEntries(detail.hypotheses.map(hypothesis => [hypothesis.id, 'pending'])))
    changed()
  }
  async function refreshAll() {
    setRefreshed(false); setError(null)
    const results = await Promise.allSettled([refresh(), complex.refresh()])
    if (results.every(result => result.status === 'fulfilled' && (!complexId || result.value !== null))) setRefreshed(true)
    else setError('Не удалось обновить все данные. Черновик сохранён; повторите обновление.')
  }
  async function save(event: FormEvent) {
    event.preventDefault()
    if (busy || conflict || stale || materialLoading || complex.loading) return
    const selected = detail.hypotheses.flatMap(hypothesis => {
      const decision = decisions[hypothesis.id] || hypothesis.decision
      return decision === 'pending' ? [] : [{ hypothesisId: hypothesis.id, decision }]
    })
    const confirming = selected.filter(item => item.decision === 'confirmed')
    if (confirming.length && (!complexId || !complex.data || complex.data.id !== complexId)) { setError('Для подтверждения выберите ЖК и дождитесь его загрузки.'); return }
    if (complexId && (!complex.data || complex.data.id !== complexId || complex.error)) { setError('Не удалось проверить актуальную версию выбранного ЖК. Обновите данные.'); return }
    if (confirming.some(item => {
      const hypothesis = detail.hypotheses.find(row => row.id === item.hypothesisId)!
      return !hypothesis.quote.trim() || !records.some(record => record.id === hypothesis.occurrenceId
        && (Boolean(record.text.trim()) || record.media.some(media => media.kind === 'image' && media.availability !== 'unavailable')))
    })) { setError('Перед подтверждением загрузите и сверьте оригинал каждой выбранной цитаты.'); return }
    const payload = { expectedVersion: detail.version, revisionId: detail.revisionId, complexId: complexId || null,
      expectedComplexVersion: complexId ? complex.data!.version : null, decisions: selected, notes, disposition }
    const serialized = JSON.stringify(payload)
    if (request.current?.serialized !== serialized) request.current = { serialized, id: crypto.randomUUID() }
    setBusy(true); setError(null); setSuccess(null)
    try {
      const saved = await api<MaterialDetail>(`/api/v1/materials/${encodeURIComponent(detail.id)}/review`, { method: 'POST', body: JSON.stringify({ requestId: request.current!.id, ...payload }) })
      apply(saved); setAcknowledged(`${saved.version}:${saved.revisionId}`); setNotes(saved.review?.notes || notes)
      setDecisions({}); setDirty(false); setConflict(false); setRefreshed(false); request.current = null
      setSuccess('Проверка сохранена. Подтверждённые риски показаны по ответу сервера.')
      if (complexId) void complex.refresh().catch(() => {})
    } catch (failure) {
      setError(failure instanceof ApiError && failure.status === 422 ? 'Проверка не сохранена: недостаточно доказательств или недопустимое решение. Сверьте оригиналы и выбранный ЖК.' : errorMessage(failure))
      if (failure instanceof ApiError && failure.status === 409) { setConflict(true); setRefreshed(false) }
    } finally { setBusy(false) }
  }
  async function retryAnalysis() {
    if (busy || dirty || detail.analysis.status !== 'failed' || !detail.analysis.canRetry || conflict || stale) return
    if (analysisRequest.current?.version !== detail.version) analysisRequest.current = { version: detail.version, id: crypto.randomUUID() }
    setBusy(true); setError(null)
    try {
      const saved = await api<MaterialDetail>(`/api/v1/materials/${encodeURIComponent(detail.id)}/retry-analysis`, { method: 'POST', body: JSON.stringify({ requestId: analysisRequest.current.id, expectedVersion: detail.version }) })
      apply(saved); setAcknowledged(`${saved.version}:${saved.revisionId}`)
    } catch (failure) {
      setError(errorMessage(failure)); if (failure instanceof ApiError && failure.status === 409) setConflict(true)
    } finally { setBusy(false) }
  }
  return <div className="ad-stack">
    <section className="panel content-pad ad-panel ad-stack"><PriorityView value={detail.priority} /><AnalysisView value={detail.analysis} />
      {detail.analysis.status === 'failed' && detail.analysis.canRetry && <Button variant="outline" disabled={busy || dirty || stale || conflict} onClick={() => void retryAnalysis()}>Повторить после ошибки анализа</Button>}
      <Button variant="outline" disabled={busy || materialLoading || complex.loading} onClick={() => void refreshAll()}>Обновить материал и ЖК</Button>
      {detail.review && <p className="form-hint">Предыдущая проверка: {formatDate(detail.review.reviewedAt)} · {detail.review.reviewerDisplayName || 'Аналитик'}. Сохранённые решения остаются в истории.</p>}
    </section>
    <div className="ad-grid"><div className="ad-stack">
      <Originals key={`${detail.id}:${detail.revisionId}:${detail.version}`} detail={detail} requestedId={requested} onRecords={setRecords} />
      {detail.occurrences.some(record => record.legacyKind === 'advertisement') && <details className="panel content-pad ad-panel" onToggle={event => setUploadOpen(event.currentTarget.open)}><summary>Добавить изображение к исходному материалу</summary>
        {uploadOpen && <ScreenshotUpload adId={detail.occurrences.find(record => record.legacyKind === 'advertisement')!.legacyId} disabled={dirty || busy} changed={refreshAll} onBusy={setBusy} />}
      </details>}
      <section className="panel content-pad ad-panel ad-stack"><h2>ЖК и документы</h2>
        <p>Связь с ЖК сохраняется вместе с проверкой. Отсутствие сведений о разрешении не подтверждает R1.</p>
        <ComplexPicker label="ЖК материала" value={complexId} selectedName={detail.complex?.id === complexId ? detail.complex.name : undefined} disabled={busy} onChange={chooseComplex} />
        {detail.complexCandidates.length > 0 && <details><summary>Кандидаты из анализа — требуют выбора</summary><div className="ad-stack">{detail.complexCandidates.map(candidate => <div key={candidate.id}><strong>{candidate.name}</strong><p>{candidate.address}</p><Button variant="outline" disabled={busy} onClick={() => chooseComplex(candidate.id)}>Выбрать ЖК: {candidate.name}</Button></div>)}</div></details>}
        {complex.loading ? <LoadingState /> : complex.error ? <ErrorState message={complex.error} retry={() => void complex.refresh().catch(() => {})} /> : complex.data && <>
          <h3>{complex.data.name}</h3><p>{complex.data.address}</p>
          <p>Основание: {basisLabels[complex.data.legalBasis.type]} · {statusLabels[complex.data.legalBasis.status === 'disproved' ? 'rejected' : complex.data.legalBasis.status]}.</p>
          <p>{complex.data.legalBasis.reference || 'Реквизиты не указаны'}</p><p>{complex.data.legalBasis.source || 'Источник проверки не указан'}</p>
          <Link className="detail-link" to={`/complexes/${encodeURIComponent(complexId)}?tab=documents`}>Документы и источники ЖК →</Link>
          <Link className="detail-link" to={`/complexes/${encodeURIComponent(complexId)}?tab=history`}>История решений ЖК →</Link>
          <details><summary>Справочные источники для проверки документов</summary><PublicSources complexId={complexId} demo={complex.data.demo} /></details>
        </>}
      </section>
      {records.some(record => record.legacyKind === 'advertisement') && <details className="panel content-pad ad-panel" onToggle={event => setTraceOpen(event.currentTarget.open)}><summary>Рекламный след и файлы исходных объявлений</summary>
        {traceOpen && records.filter(record => record.legacyKind === 'advertisement').map(record => <section key={record.id} className="ad-stack"><h3>{record.platform} · {record.account}</h3><Link className="detail-link" to={`/advertising/legacy/advertisement/${encodeURIComponent(record.legacyId)}`}>Файлы и история исходного объявления →</Link><TracePanel adId={record.legacyId} /></section>)}
      </details>}
    </div><div className="ad-stack">
      <section className="panel content-pad ad-panel"><h2>Решение по материалу</h2>
        <p className="form-hint">Сверьте оригиналы и выберите решение для каждой нужной гипотезы. «Подтверждаю» относится только к указанной цитате и выбранному ЖК. Проверка и баллы сохраняются одной операцией на сервере.</p>
        <form className="ad-form" onSubmit={save}>
          {!detail.hypotheses.length && <p>Поддержанных гипотез нет. Это не подтверждение безопасности объекта.</p>}
          {detail.hypotheses.map((hypothesis, index) => <section className="ad-hypothesis" key={hypothesis.id}>
            <h3>{hypothesis.code} · {factorLabels[hypothesis.code]}</h3><p>Гипотеза для проверки, не установленное нарушение.</p>
            <blockquote>{hypothesis.quote}</blockquote><p>{hypothesis.explanation}</p>
            <Button type="button" variant="outline" onClick={() => setRequested(hypothesis.occurrenceId)}>Показать оригинал цитаты</Button>
            <FormField label={`Решение по гипотезе ${index + 1} (${hypothesis.code})`}><select value={decisions[hypothesis.id] || hypothesis.decision} disabled={busy} onChange={event => { setDecisions(previous => ({ ...previous, [hypothesis.id]: event.target.value as Decision | 'pending' })); changed() }}>
              <option value="pending">Не выбрано</option><option value="confirmed">Подтверждаю</option><option value="rejected">Отклоняю</option><option value="insufficient">Недостаточно данных</option>
            </select></FormField>
          </section>)}
          {complexId !== (detail.complex?.id || '') && detail.confirmedRisk?.factors.some(factor => factor.status === 'confirmed') && <p className="inline-notice">Вы меняете ЖК. Прежние подтверждённые факторы не переносятся автоматически; допустимость решения проверит сервер.</p>}
          <FormField label="Общий комментарий"><textarea value={notes} required maxLength={2000} rows={5} disabled={busy} onChange={event => { setNotes(event.target.value); changed() }} /></FormField>
          <FormField label="Итог проверки"><select value={disposition} disabled={busy} onChange={event => { setDisposition(event.target.value as ReviewBody['disposition']); changed() }}><option value="reviewed">Проверено</option><option value="needs_review">Оставить для проверки</option><option value="dismissed">Отложить</option></select></FormField>
          {(conflict || stale) && <div role="status"><p>Данные изменились. Черновик сохранён. Обновите материал и ЖК, сверьте новые оригиналы и решения. Повторной отправки без вашего действия не будет.</p>
            {refreshed && <label className="checkbox-field"><input type="checkbox" checked={false} onChange={() => { setAcknowledged(token); setConflict(false); setRefreshed(false); request.current = null }} />Я сверил обновлённые данные и готов повторить решение</label>}</div>}
          {error && <ErrorState message={error} />}{success && <p role="status" className="inline-notice">{success}</p>}
          <Button disabled={busy || materialLoading || complex.loading || conflict || stale}>{busy ? 'Сохраняем…' : 'Сохранить проверку'}</Button>
        </form>
      </section>
      <section className="panel content-pad ad-panel ad-stack"><h2>Подтверждённые риски</h2>
        <p className="form-hint">Серверная оценка только по подтверждённым R1–R6. Приоритет очереди и уверенность ИИ в неё не входят.</p>
        {detail.complex && <p>Сохранённый ЖК: {detail.complex.name}.</p>}
        {complexId !== (detail.complex?.id || '') && <p className="inline-notice">Показана прежняя сохранённая оценка. Выбранная новая связь с ЖК ещё не сохранена.</p>}
        {detail.confirmedRisk ? <><RiskBadge confirmed risk={detail.confirmedRisk} /><ul>{detail.confirmedRisk.factors.map(factor => <li key={factor.code}>{factor.code} · {factorLabels[factor.code]}: {statusLabels[factor.status]} · {factor.points} баллов</li>)}</ul></> : <p>Подтверждённая оценка для материала пока недоступна. Это не нулевой риск.</p>}
        {detail.complex && complexId === detail.complex.id && <Link className="detail-link" to={`/signals/new?complex=${encodeURIComponent(detail.complex.id)}`}>Создать сигнал по проверенным данным ЖК →</Link>}
      </section>
      <MaterialHistory id={detail.id} version={detail.version} />
    </div></div>
  </div>
}

export function MaterialReviewPage() {
  const { id } = useParams()
  const { search } = useLocation()
  const material = useResource<MaterialDetail>(id ? `/api/v1/materials/${encodeURIComponent(id)}` : null)
  return <div className="advertising"><Link className="back-link" to={'/advertising' + search}>← Все материалы</Link>
    <PageHeading eyebrow="Реклама · проверка" title={material.data?.title || 'Проверка материала'} description="Оригиналы, связь с ЖК и одно сохранение выбранных решений." />
    {material.error && <ErrorState message={material.error} retry={() => void material.refresh().catch(() => {})} />}
    {!material.data ? material.loading ? <LoadingState /> : null : <ReviewEditor key={material.data.id} detail={material.data} materialLoading={material.loading} refresh={material.refresh} apply={material.apply} />}
  </div>
}

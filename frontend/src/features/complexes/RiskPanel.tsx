import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { EditorHeading, ErrorState, FormField, LoadingState, RiskBadge, StatusBadge } from '@/components/WorkspaceUI'
import { useAuth } from '@/features/auth/AuthProvider'
import { factorLabels } from '@/lib/labels'
import { useApiQuery } from '@/lib/useApiQuery'
import { useReviewRecord } from '@/lib/useReviewRecord'
import type { Complex, Evidence, FactorCode, Page } from '@/lib/types'

export function RiskPanel({ complex_: initialComplex, onChanged }: { complex_: Complex; onChanged: () => void }) {
  const { api } = useAuth()
  const record = useReviewRecord(initialComplex, `/api/v1/complexes/${initialComplex.id}`)
  const complex_ = record.current
  const [selected, setSelected] = useState<FactorCode | null>(null)
  const [cursor, setCursor] = useState('')
  const [pickedIds, setPickedIds] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const error = record.error
  const evidence = useApiQuery<Page<Evidence>>(selected ? `/api/v1/complexes/${complex_.id}/evidence?limit=100&status=confirmed${cursor ? `&cursor=${cursor}` : ''}` : null)
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setBusy(true); record.clearError()
    try {
      if (form.get('decision') === 'confirmed' && !pickedIds.length) throw new Error('Выберите проверенное доказательство для подтверждения фактора.')
      await api(`/api/v1/complexes/${complex_.id}/factors/decision`, { method: 'POST', body: JSON.stringify({
        code: selected, decision: form.get('decision'), evidenceIds: pickedIds,
        notes: form.get('notes'), expectedVersion: complex_.version,
      }) })
      setSelected(null); onChanged()
    } catch (error) { record.failed(error) } finally { setBusy(false) }
  }
  return <aside className="panel risk-panel" aria-label="Приоритет и решения по факторам"><div className="panel-heading"><h2>Приоритет проверки</h2><span className="text-xs text-muted-foreground">R1–R6</span></div>
    <div className="risk-total"><strong>{complex_.risk.score}<small>/100</small></strong><RiskBadge risk={complex_.risk} /></div>
    <p className="risk-description">Учитываются только подтверждённые факторы с проверенными доказательствами.</p>
    <div className="factor-list">{complex_.risk.factors.map((factor) => <div key={factor.code} className="factor-item">
      <div className="factor-top"><span className="factor-code">{factor.code}</span><strong>{factorLabels[factor.code]}</strong><span className="factor-points">{factor.points}<small>/{factor.weight}</small></span></div>
      <div className="factor-bottom"><StatusBadge status={factor.status} /><button type="button" className="text-action" id={`factor-trigger-${factor.code}`} aria-label={`Решение по фактору ${factor.code}`} aria-expanded={selected === factor.code} disabled={busy || record.refreshing} onClick={() => { setSelected(factor.code); setCursor(''); setPickedIds([...factor.evidenceIds]); record.clearError() }}>Решение по фактору</button></div>
      {factor.evidenceIds.map((id, index) => <Link className="detail-link mt-2 mr-3" key={id} to={`/complexes/${complex_.id}?tab=evidence&source=${id}`}>Источник {index + 1}</Link>)}
    </div>)}</div>
    {selected && <form className="editor-form" key={selected} onSubmit={submit} aria-busy={busy}><EditorHeading>Решение по {selected}</EditorHeading><p className="text-sm">{factorLabels[selected]}</p>
      <p className="form-hint">Проверенный источник сам по себе не добавляет баллы. Здесь аналитик отдельно подтверждает или отклоняет фактор; результат рассчитывает сервер.</p>
      <FormField label="Решение"><select name="decision" disabled={busy} defaultValue={complex_.risk.factors.find(factor => factor.code === selected)?.status === 'confirmed' ? 'confirmed' : 'unknown'}><option value="unknown">Оставить без подтверждения</option><option value="confirmed">Подтвердить фактор</option><option value="rejected">Отклонить фактор</option></select></FormField>
      <fieldset><legend className="mb-2 text-sm font-medium">Проверенные доказательства</legend>
        {evidence.loading && <LoadingState />}
        {evidence.data?.items.filter((item) => item.status === 'confirmed').map((item) => <label className="checkbox-field" key={item.id}><input type="checkbox" name="evidenceIds" value={item.id} checked={pickedIds.includes(item.id)} disabled={busy || (!pickedIds.includes(item.id) && pickedIds.length >= 30)} onChange={(event) => setPickedIds((ids) => event.target.checked ? [...ids, item.id] : ids.filter((id) => id !== item.id))} /><span>{item.excerpt.slice(0, 110)}</span></label>)}
        <p className="form-hint">Выбрано источников: {pickedIds.length} / 30</p>
        {(cursor || evidence.data?.nextCursor) && <div className="form-actions"><Button type="button" variant="outline" onClick={() => setCursor('')}>В начало</Button>{evidence.data?.nextCursor && <Button type="button" variant="outline" onClick={() => setCursor(evidence.data!.nextCursor!)}>Ещё источники</Button>}</div>}
        {evidence.error && <ErrorState message={evidence.error} retry={evidence.refresh} />}
        {!evidence.loading && !evidence.data?.items.some((item) => item.status === 'confirmed') && <p className="form-hint">Сначала подтвердите подходящий источник во вкладке «Доказательства».</p>}
      </fieldset>
      <FormField label="Обоснование"><textarea name="notes" rows={3} maxLength={5000} required disabled={busy} /></FormField>
      {complex_.version !== initialComplex.version && <p className="inline-notice">Актуальная версия ЖК: {complex_.version}. Балл и статусы выше получены с сервера. Ваши поля сохранены; сверьте их перед повторным решением.</p>}
      {error && <ErrorState message={error} />}
      {record.conflict && <Button type="button" variant="outline" disabled={record.refreshing} onClick={() => { void record.refresh().then(() => evidence.refresh()) }}>{record.refreshing ? 'Обновляем данные…' : 'Обновить данные ЖК'}</Button>}
      <div className="form-actions"><Button disabled={busy || evidence.loading || record.conflict || record.refreshing}>{busy ? 'Сохраняем решение…' : 'Сохранить решение'}</Button><Button type="button" variant="outline" disabled={busy || record.refreshing} onClick={() => { document.getElementById(`factor-trigger-${selected}`)?.focus(); setSelected(null) }}>Отмена</Button></div>
    </form>}
    <p className="risk-disclaimer">Баллы не устанавливают незаконность. Высокий приоритет требует проверки человеком.</p>
  </aside>
}

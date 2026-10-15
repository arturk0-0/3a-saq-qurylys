import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { ErrorState, FormField, RiskBadge, StatusBadge } from '@/components/WorkspaceUI'
import { useAuth } from '@/features/auth/AuthProvider'
import { errorMessage, factorLabels } from '@/lib/labels'
import { useApiQuery } from '@/lib/useApiQuery'
import type { Complex, Evidence, FactorCode, Page } from '@/lib/types'

export function RiskPanel({ complex_, onChanged }: { complex_: Complex; onChanged: () => void }) {
  const { api } = useAuth()
  const [selected, setSelected] = useState<FactorCode | null>(null)
  const [cursor, setCursor] = useState('')
  const [pickedIds, setPickedIds] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const evidence = useApiQuery<Page<Evidence>>(selected ? `/api/v1/complexes/${complex_.id}/evidence?limit=100&status=confirmed${cursor ? `&cursor=${cursor}` : ''}` : null)
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setBusy(true); setError(null)
    try {
      await api(`/api/v1/complexes/${complex_.id}/factors/decision`, { method: 'POST', body: JSON.stringify({
        code: selected, decision: form.get('decision'), evidenceIds: pickedIds,
        notes: form.get('notes'), expectedVersion: complex_.version,
      }) })
      setSelected(null); onChanged()
    } catch (error) { setError(errorMessage(error)) } finally { setBusy(false) }
  }
  return <aside className="panel risk-panel"><div className="panel-heading"><h2>Приоритет проверки</h2><span className="text-xs text-muted-foreground">R1–R6</span></div>
    <div className="risk-total"><strong>{complex_.risk.score}<small>/100</small></strong><RiskBadge risk={complex_.risk} /></div>
    <p className="risk-description">Учитываются только подтверждённые факторы с проверенными доказательствами.</p>
    <div className="factor-list">{complex_.risk.factors.map((factor) => <div key={factor.code} className="factor-item">
      <div className="factor-top"><span className="factor-code">{factor.code}</span><strong>{factorLabels[factor.code]}</strong><span className="factor-points">{factor.points}<small>/{factor.weight}</small></span></div>
      <div className="factor-bottom"><StatusBadge status={factor.status} /><button type="button" className="text-action" onClick={() => { setSelected(factor.code); setCursor(''); setPickedIds([]); setError(null) }}>Пересмотреть</button></div>
      {factor.evidenceIds.map((id, index) => <Link className="detail-link mt-2 mr-3" key={id} to={`/complexes/${complex_.id}?tab=evidence&source=${id}`}>Источник {index + 1}</Link>)}
    </div>)}</div>
    {selected && <form className="editor-form" onSubmit={submit}><h3 className="font-semibold">Решение по {selected}</h3><p className="text-sm">{factorLabels[selected]}</p>
      <FormField label="Решение"><select name="decision" defaultValue="unknown"><option value="unknown">Оставить без подтверждения</option><option value="confirmed">Подтвердить фактор</option><option value="rejected">Отклонить фактор</option></select></FormField>
      <fieldset><legend className="mb-2 text-sm font-medium">Проверенные доказательства</legend>
        {evidence.data?.items.filter((item) => item.status === 'confirmed').map((item) => <label className="checkbox-field" key={item.id}><input type="checkbox" name="evidenceIds" value={item.id} checked={pickedIds.includes(item.id)} disabled={!pickedIds.includes(item.id) && pickedIds.length >= 30} onChange={(event) => setPickedIds((ids) => event.target.checked ? [...ids, item.id] : ids.filter((id) => id !== item.id))} /><span>{item.excerpt.slice(0, 110)}</span></label>)}
        <p className="form-hint">Выбрано источников: {pickedIds.length} / 30</p>
        {(cursor || evidence.data?.nextCursor) && <div className="form-actions"><Button type="button" variant="outline" onClick={() => setCursor('')}>В начало</Button>{evidence.data?.nextCursor && <Button type="button" variant="outline" onClick={() => setCursor(evidence.data!.nextCursor!)}>Ещё источники</Button>}</div>}
        {evidence.error && <ErrorState message={evidence.error} retry={evidence.refresh} />}
        {!evidence.loading && !evidence.data?.items.some((item) => item.status === 'confirmed') && <p className="form-hint">Сначала подтвердите подходящий источник во вкладке «Доказательства».</p>}
      </fieldset>
      <FormField label="Обоснование"><textarea name="notes" rows={3} maxLength={5000} required /></FormField>
      {error && <ErrorState message={error} />}
      <div className="form-actions"><Button disabled={busy || evidence.loading}>Сохранить решение</Button><Button type="button" variant="outline" onClick={() => setSelected(null)}>Отмена</Button></div>
    </form>}
    <p className="risk-disclaimer">Баллы не устанавливают незаконность. Высокий приоритет требует проверки человеком.</p>
  </aside>
}

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { ErrorState, LoadingState } from '@/components/WorkspaceUI'
import { useApiQuery } from '@/lib/useApiQuery'

interface Candidate { complexId: string; name: string; city: string; matchedBy: 'name' | 'alias' | 'partial_name'; matchedName: string; demo: boolean }
interface Matches { currentComplexId: string; catalogLimited: boolean; groups: { mention: string; ambiguous: boolean;
  candidateCount: number; candidatesLimited: boolean; candidates: Candidate[] }[] }
const reasons = { name: 'Совпало название', alias: 'Совпало альтернативное название', partial_name: 'Частичное совпадение слов' }

export function MatchingCandidates({ adId, runId }: { adId: string; runId: string }) {
  const [enabled, setEnabled] = useState(false)
  const [selected, setSelected] = useState<Candidate | null>(null)
  const { data, loading, error, refresh } = useApiQuery<Matches>(enabled
    ? `/api/v1/advertisements/${encodeURIComponent(adId)}/matching-candidates?run_id=${encodeURIComponent(runId)}` : null)
  return <section aria-label="Сравнение названий ЖК" className="mt-3">
    <Button size="sm" variant="outline" aria-expanded={enabled} onClick={() => setEnabled(!enabled)}>{enabled ? 'Скрыть кандидатов ЖК' : 'Найти ЖК по названиям'}</Button>
    {enabled && <div className="mt-3">
      <p className="form-hint">Это подсказки по названиям и алиасам внутреннего реестра. Выбор ниже открывает сравнение; привязка объявления и баллы остаются прежними.</p>
      {loading ? <LoadingState /> : error ? <ErrorState message={error} retry={refresh} /> : data?.groups.map((group, index) => <div className="evidence-card my-3" key={`${index}-${group.mention}`}>
        <strong>Название по версии AI: {group.mention}</strong>
        {group.ambiguous && <p className="inline-notice">Неоднозначно: найдено {group.candidateCount} ЖК. Сравните адрес, город и оригинал; автоматического выбора нет.</p>}
        {!group.candidates.length && <p className="form-hint">Совпадений в проверенной части реестра нет. Это не означает отсутствие правового основания и не даёт R1.</p>}
        {group.candidates.map((candidate) => <div className="my-3" key={candidate.complexId}>
          <p>{candidate.name} · {candidate.city}{candidate.demo ? ' · DEMO' : ''}</p>
          <p className="form-hint">{reasons[candidate.matchedBy]}: {candidate.matchedName}. {candidate.complexId === data.currentComplexId && 'Текущая привязка объявления.'}</p>
          <Button size="sm" variant="outline" aria-label={`Сравнить: ${candidate.name}`} aria-pressed={selected?.complexId === candidate.complexId} onClick={() => setSelected(candidate)}>Выбрать для сравнения</Button>
        </div>)}
        {group.candidatesLimited && <p className="form-hint">Показаны первые 10 кандидатов. Уточните объект в реестре.</p>}
      </div>)}
      {data?.catalogLimited && <p className="inline-notice">Поиск ограничен первыми 500 записями. Полнота совпадений не гарантируется.</p>}
      {selected && <div className="inline-notice"><p>Для сравнения выбран: {selected.name}.</p>
        {selected.complexId !== data?.currentComplexId && <p>Кандидат отличается от текущей привязки. Проверьте исходное объявление с аналитиком.</p>}
        <Link className="detail-link" to={`/complexes/${encodeURIComponent(selected.complexId)}`}>Открыть выбранный ЖК →</Link>
      </div>}
    </div>}
  </section>
}

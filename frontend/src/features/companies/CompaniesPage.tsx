import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { ErrorState, FormField, LoadingState, PageHeading } from '@/components/WorkspaceUI'
import { useAuth } from '@/features/auth/AuthProvider'
import { errorMessage, formatDate, stageLabels } from '@/lib/labels'
import { useApiQuery } from '@/lib/useApiQuery'
import { CitationLink } from './CitationLink'
import type { Candidate, Preview } from './types'
import './companies.css'

export function CompaniesPage() {
  const { api } = useAuth()
  const [cursor, setCursor] = useState('')
  const companies = useApiQuery<{ items: { id: string; name: string; bin: string }[]; nextCursor: string | null }>('/api/v1/companies?limit=20' + (cursor ? '&cursor=' + cursor : ''))
  const [q, setQ] = useState('')
  const [results, setResults] = useState<{ items: Candidate[]; limited: boolean } | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [importToRegistry, setImport] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState<{ companyIds: string[]; registryId: string | null } | null>(null)
  async function operation(action: 'search' | 'preview' | 'save', recordId?: string, event?: FormEvent) {
    event?.preventDefault(); setBusy(true); setError(null)
    try {
      if (action === 'search') {
        setPreview(null); setSaved(null); setImport(false)
        setResults(await api('/api/v1/company-projects/search?q=' + encodeURIComponent(q.trim())))
      } else if (action === 'preview') {
        setPreview(null); setSaved(null); setImport(false)
        setPreview(await api('/api/v1/company-projects/' + recordId))
      } else if (preview) {
        setSaved(await api('/api/v1/company-projects/' + preview.project.recordId, { method: 'POST', body: JSON.stringify({
          expectedVersion: preview.savedVersion, expectedDocumentSha256: preview.project.documentSha256, importToRegistry,
        }) }))
        setPreview(null); companies.refresh()
      }
    } catch (failure) { setError(errorMessage(failure)) } finally { setBusy(false) }
  }
  return <div className="company-feature"><PageHeading eyebrow="Сведения из открытых источников" title="Организации" description="Застройщики и уполномоченные компании, связанные с найденными ЖК." />
    <section className="panel"><h2>Найти участников по жилому комплексу</h2><p>Введите название ЖК или адрес. Сверьте карточку источника перед сохранением.</p>
      <form className="company-search" onSubmit={e => void operation('search', undefined, e)}><FormField label="Название ЖК или адрес"><input required minLength={3} maxLength={100} value={q} disabled={busy} onChange={e => setQ(e.target.value)} /></FormField><Button disabled={busy || q.trim().length < 3}>Найти в Homeportal</Button></form>
      {busy && <LoadingState />}{error && <ErrorState message={error} />}
      {results && <><p className="form-hint">Поиск ограничен каталогом ВКО. Пустой результат не означает отсутствия организации или разрешения.</p>
        {results.items.length === 0 && <p>Совпадений не найдено. Попробуйте другое название или адрес.</p>}
        {results.items.map(candidate => <article className="company-project" key={candidate.recordId}><h3>{candidate.name}</h3><p>{candidate.address}</p><p>Застройщик: {candidate.developer || 'Не указан'} · Уполномоченная компания: {candidate.holder || 'Не указана'}</p><Button variant="outline" disabled={busy} onClick={() => void operation('preview', candidate.recordId)}>Посмотреть участников</Button></article>)}
        {results.limited && <p>Показана часть результатов. Уточните запрос.</p>}</>}
      {preview && <section className="company-preview"><h3>{preview.project.name}</h3><p>{preview.project.city} · {preview.project.address}</p><CitationLink source={preview.project.source} /><p>Получено {formatDate(preview.project.source.retrievedAt)}</p>
        {preview.project.parties.map(party => <article key={party.role}><strong>{party.role === 'developer' ? 'Юридический застройщик' : 'Уполномоченная компания'}</strong><p>{party.name} · БИН {party.bin}</p></article>)}
        <p>Этап: {preview.project.stage ? stageLabels[preview.project.stage] + ' — по данным каталога' : 'Не уточнён'}</p>
        <p>{preview.project.coordinates ? 'В карточке есть точка объекта; точность требует сверки.' : 'Достоверная точка объекта не установлена. На карте она не подставляется.'}</p>
        <label className="company-check"><input type="checkbox" checked={importToRegistry} disabled={busy || !preview.canImportToRegistry || !preview.project.stage || !preview.project.parties.some(p => p.role === 'developer')} onChange={e => setImport(e.target.checked)} /><span>Также добавить отдельный реальный ЖК в реестр</span></label>
        {!preview.canImportToRegistry && <p className="form-hint">Добавление реальных ЖК сейчас недоступно. Участников можно сохранить отдельно.</p>}
        <div className="form-actions"><Button disabled={busy} onClick={() => void operation('save')}>Сохранить участников</Button><Button variant="outline" disabled={busy} onClick={() => void operation('preview', preview.project.recordId)}>Обновить карточку источника</Button></div>
      </section>}
      {saved && <div role="status" className="inline-notice">Участники сохранены с источниками. {saved.companyIds.map(id => <Link key={id} className="detail-link" to={'/companies/' + id}>Открыть организацию · БИН {id.replace('bin-', '')} → </Link>)}{saved.registryId && <Link className="detail-link" to={'/complexes/' + saved.registryId}>Открыть ЖК →</Link>}</div>}
    </section>
    <section className="panel"><h2>Сохранённые организации</h2>{companies.loading ? <LoadingState /> : companies.error ? <ErrorState message={companies.error} retry={companies.refresh} /> : companies.data?.items.length ? companies.data.items.map(company => <article className="company-project" key={company.id}><Link className="detail-link" to={'/companies/' + company.id}>{company.name} →</Link><p>БИН {company.bin}</p></article>) : <p>Организации пока не сохранены. Найдите ЖК в источнике или откройте участника из существующей карточки.</p>}
      {(cursor || companies.data?.nextCursor) && <div className="form-actions"><Button variant="outline" onClick={() => setCursor('')}>В начало списка</Button>{companies.data?.nextCursor && <Button variant="outline" onClick={() => setCursor(companies.data!.nextCursor!)}>Далее</Button>}</div>}
    </section>
  </div>
}

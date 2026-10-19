import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { DemoBadge, EmptyState, ErrorState, LoadingState, PageHeading } from '@/components/WorkspaceUI'
import { useAuth } from '@/features/auth/AuthProvider'
import { errorMessage, formatDate, stageLabels } from '@/lib/labels'
import { useApiQuery } from '@/lib/useApiQuery'
import { CitationLink, safeWebUrl } from './CitationLink'
import type { Company } from './types'
import './companies.css'

const labels = { name: 'Юридическое наименование', bin: 'БИН', registrationDate: 'Дата регистрации', status: 'Статус организации', legalAddress: 'Юридический адрес', website: 'Сайт' }
export function CompanyDetail() {
  const { id } = useParams()
  const { api } = useAuth()
  const query = useApiQuery<Company>(id ? '/api/v1/companies/' + encodeURIComponent(id) : null)
  const [updated, setUpdated] = useState<Company | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const company = updated ?? query.data
  async function refreshSources() {
    if (!company) return
    setBusy(true); setError(null)
    try { setUpdated(await api<Company>('/api/v1/companies/' + encodeURIComponent(company.id) + '/refresh', { method: 'POST', body: JSON.stringify({ expectedVersion: company.version }) })) }
    catch (failure) { setError(errorMessage(failure)) } finally { setBusy(false) }
  }
  if (query.loading && !company) return <LoadingState />
  if (query.error && !company) return <ErrorState message={query.error} retry={query.refresh} />
  if (!company) return <EmptyState title="Организация не найдена" />
  const names = new Set(company.facts.filter(f => f.field === 'name').map(f => f.value))
  return <div className="company-feature"><Link className="back-link" to="/companies">← К организациям</Link>
    <PageHeading eyebrow="Участник строительства" title={names.size > 1 ? 'Организация · БИН ' + company.bin : company.name} description={'БИН ' + company.bin}
      action={company.demo ? <DemoBadge /> : company.version > 0 ? <Button variant="outline" disabled={busy} onClick={() => void refreshSources()}>{busy ? 'Обновляем…' : 'Обновить по источникам'}</Button> : undefined} />
    {error && <ErrorState message={error} />}
    {error && <Button variant="outline" onClick={() => { setUpdated(null); query.refresh() }}>Загрузить сохранённую версию</Button>}
    {company.lastError && <p role="status" className="inline-notice">Часть сведений не обновлена: источник недоступен или изменился. Сохранённые сведения и даты показаны ниже.</p>}
    <section className="panel"><h2>Основные сведения</h2><dl className="company-facts">{Object.entries(labels).map(([field, label]) => {
      const facts = company.facts.filter(f => f.field === field)
      const values = [...new Set(facts.map(f => f.value))]
      return <div key={field}><dt>{label}</dt><dd>{!facts.length ? field === 'name' || field === 'bin' ? <><span>{field === 'name' ? company.name : company.bin}</span><small>Внутренняя запись, публичный источник не указан</small></> : <span className="company-unknown">Сведения пока не найдены</span>
        : <>{values.length > 1 && <p className="inline-notice">В сохранённых источниках есть различающиеся сведения. Сверьте значения и даты.</p>}{values.map(value => <div className="company-fact-value" key={value}>
          {field === 'website' && safeWebUrl(value) ? <a href={safeWebUrl(value)!} target="_blank" rel="noopener noreferrer">{value}</a> : <span>{value}</span>}
          {facts.filter(f => f.value === value).map(f => <CitationLink key={f.source.url} source={f.source} />)}
        </div>)}</>}</dd></div>
    })}</dl></section>
    <section className="panel"><h2>Объекты в найденных источниках</h2>
      <p>{company.foundCompletedCount === null ? 'Количество завершённых объектов не установлено.' : 'Найдено карточек с реквизитами зарегистрированного акта ввода: ' + company.foundCompletedCount + '.'}</p>
      <p className="form-hint">Показаны сохранённые карточки источников. Это не полный портфель компании; корпус и очередь могут быть отдельными объектами.</p>
      {!company.projects.length ? <p>Связанные объекты пока не найдены.</p> : company.projects.map(project => <article className="company-project" key={project.recordId}>
        <h3>{project.name}</h3><p>{project.city} · {project.address}</p>
        <p>{project.parties.filter(p => p.bin === company.bin).map(p => p.role === 'developer' ? 'Юридический застройщик' : 'Уполномоченная компания').join(' · ')}</p>
        <p>{project.stage ? stageLabels[project.stage] + ' — по данным источника' : 'Этап строительства не уточнён'} {project.stageSource && <CitationLink source={project.stageSource} />}</p>
        {project.commissioningReference && <p>Акт ввода: {project.commissioningReference} от {project.commissioningDate}</p>}
        <CitationLink source={project.source} /><p className="form-hint">Получено {formatDate(project.source.retrievedAt)}</p>
      </article>)}
    </section>
    {company.updatedAt && <p className="form-hint">Сведения получены {formatDate(company.updatedAt)}. Ссылки ведут на текущие страницы источников; их содержимое может измениться.</p>}
  </div>
}

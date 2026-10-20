import { useEffect, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { EmptyState, ErrorState, FormField, LoadingState, PageHeading } from '@/components/WorkspaceUI'
import { AdvertisementForm } from '@/features/advertisements/AdvertisementsPage'
import { useApiQuery } from '@/lib/useApiQuery'
import { formatDate } from '@/lib/labels'
import { AdvertisingTabs, AnalysisView, PriorityView, reviewLabels } from './presentation'
import { materialQuery, changedFilter } from './filters'
import { ComplexPicker } from './ComplexPicker'
import { SourcesSchedule } from './SourcesSchedule'
import type { MaterialPage, MaterialSummary } from './types'
import './advertising.css'

function Materials() {
  const [params, setParams] = useSearchParams()
  const { search } = useLocation()
  const [query, setQuery] = useState(params.get('q') || '')
  const [creating, setCreating] = useState(false)
  const [saved, setSaved] = useState(false)
  const [complexFilterOpen, setComplexFilterOpen] = useState(false)
  const result = useApiQuery<MaterialPage<MaterialSummary>>('/api/v1/materials?' + materialQuery(params))
  useEffect(() => { setQuery(params.get('q') || '') }, [params])
  useEffect(() => {
    const timer = window.setInterval(() => { if (document.visibilityState === 'visible' && !creating) result.refresh() }, 30000)
    return () => window.clearInterval(timer)
  }, [result.refresh, creating])
  function change(key: string, value: string) { setParams(changedFilter(params, key, value)) }
  return <div className="ad-stack">
    <section className="panel content-pad ad-panel"><h2>Поиск материалов</h2><div className="ad-filters">
      <FormField label="Поиск рекламы"><input value={query} onChange={event => setQuery(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') change('q', query) }} placeholder="Текст или название" /></FormField>
      <FormField label="Необходимость проверки"><select value={params.get('review') || 'all'} onChange={event => change('review', event.target.value)}><option value="all">Все материалы</option><option value="needs_review">Требуют проверки</option><option value="reviewed">Проверенные</option><option value="dismissed">Отложенные</option></select></FormField>
      <FormField label="Способ добавления"><select value={params.get('origin') || 'all'} onChange={event => change('origin', event.target.value)}><option value="all">Любой</option><option value="automatic">Автоматически</option><option value="manual">Вручную</option></select></FormField>
      <FormField label="Платформа"><input value={params.get('platform') || ''} onChange={event => change('platform', event.target.value)} placeholder="Например, Instagram" /></FormField>
      <FormField label="Сортировка материалов"><select value={params.get('sort') || 'priority'} onChange={event => change('sort', event.target.value)}><option value="priority">Сначала требующие проверки, по приоритету</option><option value="recent">По последнему появлению</option></select></FormField>
      <details onToggle={event => setComplexFilterOpen(event.currentTarget.open)}><summary>Фильтр по ЖК</summary>{complexFilterOpen && <ComplexPicker label="ЖК в фильтре" value={params.get('complexId') || ''} onChange={id => change('complexId', id)} />}</details>
    </div><div className="form-actions mt-4"><Button onClick={() => change('q', query)}>Найти материалы</Button><Button variant="outline" onClick={result.refresh}>Обновить материалы</Button>
      <Button variant="outline" onClick={() => { setCreating(value => !value); setSaved(false) }}>{creating ? 'Закрыть добавление' : 'Добавить материал'}</Button></div></section>
    {creating && <section className="panel content-pad ad-panel"><AdvertisementForm onCancel={() => setCreating(false)} onSaved={() => { setCreating(false); setSaved(true); change('cursor', ''); result.refresh() }} /></section>}
    {saved && <p className="inline-notice" role="status">Оригинал сохранён. Поддерживаемый материал поступит в очередь автоматического анализа; подтвердить выводы сможет только человек.</p>}
    {result.loading ? <LoadingState /> : result.error ? <ErrorState message={result.error} retry={result.refresh} /> : !result.data?.items.length ? <EmptyState title="Материалов пока нет"><p>Измените фильтры, добавьте публикацию или проверьте источники и расписание.</p></EmptyState>
      : result.data.items.map(item => <article className="panel content-pad ad-panel ad-stack" key={item.id}>
        <div className="ad-meta"><span>{reviewLabels[item.reviewState]}</span><span>{item.platforms.join(' · ') || 'Платформа не указана'}</span><span>Публикаций: {item.occurrenceCount}</span><span>{item.origins.map(origin => origin === 'manual' ? 'Вручную' : 'Автосбор').join(' · ')}</span></div>
        <h2>{item.title || 'Рекламный материал'}</h2><p className="ad-original">{item.textPreview}</p>
        <PriorityView value={item.priority} /><AnalysisView value={item.analysis} />
        <div className="form-actions"><Link className="detail-link" to={`/advertising/materials/${encodeURIComponent(item.id)}${search}`}>Проверить материал →</Link>
          {item.complex ? <Link className="detail-link" to={`/complexes/${encodeURIComponent(item.complex.id)}`}>{item.complex.name}</Link> : <span>ЖК ещё не выбран</span>}</div>
        <p className="form-hint">Последнее появление: {formatDate(item.lastSeenAt)}. Повторные публикации не увеличивают риск сами по себе.</p>
      </article>)}
    <div className="form-actions">{params.get('cursor') && <Button variant="outline" onClick={() => change('cursor', '')}>В начало материалов</Button>}
      {result.data?.nextCursor && !result.loading && <Button variant="outline" onClick={() => change('cursor', result.data!.nextCursor!)}>Следующие материалы</Button>}</div>
  </div>
}

export function AdvertisingPage() {
  const [params] = useSearchParams()
  const sources = params.get('view') === 'sources'
  return <div className="advertising"><PageHeading eyebrow="Рабочее пространство" title="Реклама" description="Оригиналы, автоматический анализ и решения аналитика." />
    <AdvertisingTabs selected={sources ? 'sources' : 'materials'} />{sources ? <SourcesSchedule /> : <Materials />}
  </div>
}

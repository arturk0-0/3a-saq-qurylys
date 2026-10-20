import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Building2, Filter, Search, ShieldCheck, ShieldAlert, ClipboardCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { DemoBadge, DetailLink, EmptyState, ErrorState, LoadingState, PageHeading, RiskBadge, ScrollableTable } from '@/components/WorkspaceUI'
import { cities, stageLabels } from '@/lib/labels'
import { useApiQuery } from '@/lib/useApiQuery'
import type { Complex, Page } from '@/lib/types'
import { ComplexMap } from './ComplexMap'
import { CityMapSection } from '@/features/city-map/CityMapSection'
import { PriorityView } from '@/features/advertising/presentation'

export function ComplexList({ overview = false }: { overview?: boolean }) {
  const [urlParams, setUrlParams] = useSearchParams()
  const search = urlParams.get('q') || ''
  const city = urlParams.get('city') || ''
  const zone = urlParams.get('zone') || ''
  const sort = urlParams.get('sort') || 'priority'
  const cursor = urlParams.get('cursor') || '0'
  const [query, setQuery] = useState(search)
  useEffect(() => { setQuery(search) }, [search])
  function updateFilter(name: string, value: string) {
    setUrlParams(previous => {
      const next = new URLSearchParams(previous)
      if (value) next.set(name, value)
      else next.delete(name)
      if (name !== 'cursor') next.delete('cursor')
      return next
    })
  }
  const [showMap, setShowMap] = useState(false)
  const params = new URLSearchParams({ q: search, sort, cursor, limit: '50' })
  if (city) params.set('city', city)
  if (zone) params.set('zone', zone)
  const { data, loading, error, refresh } = useApiQuery<Page<Complex>>(`/api/v1/complexes?${params}`)
  const visible = data?.items || []
  const stats = [
    { title: 'Объектов в выборке', value: data?.total ?? '—', icon: Building2, tone: 'neutral' },
    { title: 'Подтверждённый высокий риск', value: visible.filter((row) => row.risk.zone === 'RED').length, icon: ShieldAlert, tone: 'red' },
    { title: 'Подтверждённая жёлтая зона', value: visible.filter((row) => row.risk.zone === 'YELLOW').length, icon: ClipboardCheck, tone: 'amber' },
    { title: 'Подтверждённая зелёная зона', value: visible.filter((row) => row.risk.zone === 'GREEN').length, icon: ShieldCheck, tone: 'green' },
  ]
  return <>
    <PageHeading eyebrow="Мониторинг строительства · ВКО" title={overview ? 'Обзор рисков' : 'Реестр жилых комплексов'}
      description="Приоритет очереди и подтверждённые риски показаны отдельно. Каждое решение остаётся за аналитиком." />
    {overview && <div className="stats-grid">{stats.map(({ title, value, icon: Icon, tone }) =>
      <div className={`stat-card stat-${tone}`} key={title}><Icon size={21} /><span>{title}</span>
        <strong>{loading ? '—' : value}</strong><small>{title === 'Объектов в выборке' ? 'По текущему фильтру' : 'На текущей странице'}</small></div>)}</div>}
    <section className="panel">
      <div className="panel-heading"><div><h2>Жилые комплексы</h2><p>Каталог объектов ВКО</p></div>{overview && <div className="flex items-center gap-3"><Button variant="outline" aria-expanded={showMap} aria-controls="complex-map" onClick={() => setShowMap(!showMap)}>{showMap ? 'Скрыть карту' : 'Показать карту'}</Button></div>}</div>
      <form className="filter-bar" onSubmit={(event) => { event.preventDefault(); updateFilter('q', query) }}>
        <label className="search-input"><Search size={17} /><input aria-label="Поиск ЖК" placeholder="Название, город или адрес" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
        <select aria-label="Город" value={city} onChange={(event) => updateFilter('city', event.target.value)}>
          <option value="">Все города</option>{cities.map((name) => <option key={name}>{name}</option>)}
        </select>
        <select aria-label="Подтверждённые риски" value={zone} onChange={(event) => updateFilter('zone', event.target.value)}>
          <option value="">Все подтверждённые риски</option><option value="RED">Красная зона</option><option value="YELLOW">Жёлтая зона</option><option value="GREEN">Зелёная зона</option>
        </select>
        <select aria-label="Сортировка" value={sort} onChange={(event) => updateFilter('sort', event.target.value)}><option value="priority">По приоритету проверки</option><option value="risk">По подтверждённым рискам</option><option value="name">По названию</option></select>
        <Button type="submit" variant="outline"><Filter size={15} className="mr-2" />Найти</Button>
      </form>
      {overview && showMap && !loading && !error && <div id="complex-map"><ComplexMap complexes={visible} /></div>}
      {loading ? <LoadingState /> : error ? <ErrorState message={error} retry={refresh} />
        : !visible.length ? <EmptyState title="ЖК не найдены"><p>Измените фильтры или добавьте объекты в реестр.</p></EmptyState>
        : <ScrollableTable label="Жилые комплексы"><table className="data-table"><thead><tr><th>Жилой комплекс</th><th>Город / этап</th><th>Приоритет проверки</th><th>Подтверждённые риски</th><th><span className="sr-only">Карточка</span></th></tr></thead>
          <tbody>{visible.map((complex_) => <tr key={complex_.id}>
            <td><strong>{complex_.name.replace(/^DEMO — /, '')}</strong><span>{complex_.address}</span>{complex_.demo && <DemoBadge />}</td>
            <td><strong>{complex_.city}</strong><span>{stageLabels[complex_.stage]}</span></td>
            <td><PriorityView value={complex_.reviewPriority} /></td><td><RiskBadge confirmed risk={complex_.risk} /></td><td><DetailLink to={`/complexes/${complex_.id}`}>Карточка</DetailLink></td>
          </tr>)}</tbody></table></ScrollableTable>}
      {data?.catalogLimited && <p className="inline-notice">Поиск ограничен первыми 500 записями. Уточните город; полный поиск требует расширения индекса.</p>}
      {(cursor !== '0' || data?.nextCursor) && <div className="pagination"><Button variant="outline" onClick={() => updateFilter('cursor', '0')}>В начало</Button>
        {data?.nextCursor && <Button variant="outline" onClick={() => updateFilter('cursor', data.nextCursor!)}>Следующая страница</Button>}</div>}
    </section>
    {!overview && <CityMapSection complexes={visible} loading={loading} failed={Boolean(error)} catalogLimited={data?.catalogLimited} />}
    <p className="page-footnote">Высокий балл — основание для проверки, а не вывод о незаконности. Гипотезы AI не влияют на балл до подтверждения.</p>
  </>
}

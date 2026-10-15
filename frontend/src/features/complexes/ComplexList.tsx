import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Building2, Filter, Search, ShieldCheck, ShieldAlert, ClipboardCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { DemoBadge, DetailLink, EmptyState, ErrorState, LoadingState, PageHeading, RiskBadge, ScrollableTable } from '@/components/WorkspaceUI'
import { cities, stageLabels } from '@/lib/labels'
import { useApiQuery } from '@/lib/useApiQuery'
import type { Complex, Page } from '@/lib/types'
import { ComplexMap } from './ComplexMap'

export function ComplexList({ overview = false }: { overview?: boolean }) {
  const [urlParams, setUrlParams] = useSearchParams()
  const search = urlParams.get('q') || ''
  const city = urlParams.get('city') || ''
  const zone = urlParams.get('zone') || ''
  const sort = urlParams.get('sort') || 'risk'
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
    { title: 'Высокий приоритет', value: visible.filter((row) => row.risk.zone === 'RED').length, icon: ShieldAlert, tone: 'red' },
    { title: 'Требуют проверки', value: visible.filter((row) => row.risk.zone === 'YELLOW').length, icon: ClipboardCheck, tone: 'amber' },
    { title: 'Низкий приоритет', value: visible.filter((row) => row.risk.zone === 'GREEN').length, icon: ShieldCheck, tone: 'green' },
  ]
  return <>
    <PageHeading eyebrow="Мониторинг строительства · ВКО" title={overview ? 'Обзор рисков' : 'Реестр жилых комплексов'}
      description="Приоритет проверки по подтверждённым фактам. Каждое решение остаётся за аналитиком." />
    {overview && <div className="stats-grid">{stats.map(({ title, value, icon: Icon, tone }) =>
      <div className={`stat-card stat-${tone}`} key={title}><Icon size={21} /><span>{title}</span>
        <strong>{loading ? '—' : value}</strong><small>{title === 'Объектов в выборке' ? 'По текущему фильтру' : 'На текущей странице'}</small></div>)}</div>}
    <section className="panel">
      <div className="panel-heading"><div><h2>Жилые комплексы</h2><p>Внутренний реестр · синтетические DEMO-записи</p></div><div className="flex items-center gap-3"><Button variant="outline" aria-expanded={showMap} aria-controls="complex-map" onClick={() => setShowMap(!showMap)}>{showMap ? 'Скрыть карту' : 'Показать карту'}</Button><DemoBadge /></div></div>
      <form className="filter-bar" onSubmit={(event) => { event.preventDefault(); updateFilter('q', query) }}>
        <label className="search-input"><Search size={17} /><input aria-label="Поиск ЖК" placeholder="Название, город или адрес" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
        <select aria-label="Город" value={city} onChange={(event) => updateFilter('city', event.target.value)}>
          <option value="">Все города</option>{cities.map((name) => <option key={name}>{name}</option>)}
        </select>
        <select aria-label="Приоритет" value={zone} onChange={(event) => updateFilter('zone', event.target.value)}>
          <option value="">Все приоритеты</option><option value="RED">Высокий</option><option value="YELLOW">Требует проверки</option><option value="GREEN">Низкий</option>
        </select>
        <select aria-label="Сортировка" value={sort} onChange={(event) => updateFilter('sort', event.target.value)}><option value="risk">По баллу риска</option><option value="name">По названию</option></select>
        <Button type="submit" variant="outline"><Filter size={15} className="mr-2" />Найти</Button>
      </form>
      {showMap && !loading && !error && <div id="complex-map"><ComplexMap complexes={visible} /></div>}
      {loading ? <LoadingState /> : error ? <ErrorState message={error} retry={refresh} />
        : !visible.length ? <EmptyState title="ЖК не найдены"><p>Измените фильтры или попросите администратора загрузить DEMO-набор.</p></EmptyState>
        : <ScrollableTable label="Жилые комплексы"><table className="data-table"><thead><tr><th>Жилой комплекс</th><th>Город / этап</th><th>Готовность</th><th>Приоритет проверки</th><th><span className="sr-only">Карточка</span></th></tr></thead>
          <tbody>{visible.map((complex_) => <tr key={complex_.id}>
            <td><strong>{complex_.name.replace(/^DEMO — /, '')}</strong><span>{complex_.address}</span>{complex_.scenario && <small>Сценарий {complex_.scenario}</small>}</td>
            <td><strong>{complex_.city}</strong><span>{stageLabels[complex_.stage]}</span></td>
            <td><strong>{complex_.progress.verifiedPercent === null ? 'Не проверено' : `${complex_.progress.verifiedPercent}%`}</strong><span>Заявлено: {complex_.progress.claimedPercent ?? '—'}%</span></td>
            <td><RiskBadge risk={complex_.risk} /></td><td><DetailLink to={`/complexes/${complex_.id}`}>Карточка</DetailLink></td>
          </tr>)}</tbody></table></ScrollableTable>}
      {data?.catalogLimited && <p className="inline-notice">Поиск ограничен первыми 500 записями. Уточните город; полный поиск требует расширения индекса.</p>}
      {(cursor !== '0' || data?.nextCursor) && <div className="pagination"><Button variant="outline" onClick={() => updateFilter('cursor', '0')}>В начало</Button>
        {data?.nextCursor && <Button variant="outline" onClick={() => updateFilter('cursor', data.nextCursor!)}>Следующая страница</Button>}</div>}
    </section>
    <p className="page-footnote">Высокий балл — основание для проверки, а не вывод о незаконности. Гипотезы AI не влияют на балл до подтверждения.</p>
  </>
}

import { Component, lazy, Suspense, useMemo, useState, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { citySelection, defaultCity, type CityMapRecord } from './model'
import './city-map.css'

const CityBuildingsMap = lazy(() => import('./CityBuildingsMap').then(module => ({ default: module.CityBuildingsMap })))

class MapBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() {
    return this.state.failed ? <div className="city-map-canvas city-map-placeholder" role="status">Не удалось загрузить модуль карты. Реестр остаётся доступен. Повторите после обновления страницы.</div> : this.props.children
  }
}

export function CityMapSection({ complexes, loading, failed, catalogLimited }: {
  complexes: CityMapRecord[]; loading: boolean; failed: boolean; catalogLimited?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [city, setCity] = useState(defaultCity)
  const cities = useMemo(() => [...new Set([defaultCity, ...complexes.map(record => record.city)])].sort(), [complexes])
  const selection = useMemo(() => citySelection(complexes, city), [complexes, city])
  return <section className="city-map-feature panel" aria-label="Карта города">
    <div className="panel-heading"><div><h2>Карта города</h2><p>Условные объёмные здания на известных координатах ЖК</p></div>
      <Button variant="outline" aria-expanded={open} aria-controls="city-buildings-content" onClick={() => setOpen(value => !value)}>{open ? 'Скрыть карту города' : 'Показать карту города'}</Button></div>
    {open && <div id="city-buildings-content" className="city-map-content">
      <label className="city-map-city">Город на карте<select value={city} onChange={event => setCity(event.target.value)}>{cities.map(name => <option key={name}>{name}</option>)}</select></label>
      <p className="city-map-caption">Одинаковые модели — условное обозначение, не реальные контуры или этажность зданий. Статус «Строится» — по данным карточек.</p>
      {loading ? <p role="status">Обновляем выборку ЖК…</p> : failed ? <p role="status">Не удалось получить выборку ЖК. Повторите загрузку реестра выше.</p> : <>
        <p className="city-map-caption">На карте: {selection.located.length} из {selection.construction.length} записей со статусом «Строится» в городе {city} на текущей странице. Учитываются фильтры реестра; это не все ЖК города.</p>
        {catalogLimited && <p className="city-map-caption">Каталог ограничен серверной выборкой; часть объектов может не попасть на эту страницу.</p>}
        {selection.located.some(record => record.demo) && <p className="city-map-caption">DEMO: координаты учебных объектов условные и не указывают реальные стройки.</p>}
        {selection.missing > 0 && <p className="city-map-caption">Без корректных координат: {selection.missing}. Эти объекты остаются в таблице реестра.</p>}
        {!selection.located.length ? <p role="status">Нет объектов для карты в этой выборке. Нужны статус «Строится» и корректные координаты выбранного города. Измените город или фильтры; карточки доступны в таблице.</p>
          : <><MapBoundary><Suspense fallback={<div className="city-map-canvas city-map-placeholder" role="status">Загружаем модуль карты…</div>}><CityBuildingsMap groups={selection.groups} /></Suspense></MapBoundary>
            <p className="city-map-caption">Tab — выбор здания, Enter — сведения и ссылка на карточку. Карту можно перемещать; масштаб — кнопками +/−. Колесо мыши прокручивает страницу.</p></>}
      </>}
    </div>}
  </section>
}

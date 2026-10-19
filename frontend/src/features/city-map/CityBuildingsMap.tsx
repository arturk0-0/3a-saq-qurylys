import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { buildingIcon, buildingPopup, type citySelection } from './model'
import 'leaflet/dist/leaflet.css'

export function CityBuildingsMap({ groups }: { groups: ReturnType<typeof citySelection>['groups'] }) {
  const container = useRef<HTMLDivElement>(null)
  const [state, setState] = useState<'loading' | 'ready' | 'failed'>('loading')
  const [tileFailed, setTileFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!container.current || !groups.length) return
    let disposed = false
    let map: import('leaflet').Map | undefined
    let observer: ResizeObserver | undefined
    setState('loading'); setTileFailed(false)
    async function initialize() {
      try {
        const L = await import('leaflet')
        if (disposed || !container.current) return
        map = L.map(container.current, {
          scrollWheelZoom: false, zoomControl: false,
          zoomAnimation: false, fadeAnimation: false, markerZoomAnimation: false,
        })
        L.control.zoom({ zoomInTitle: 'Приблизить', zoomOutTitle: 'Отдалить' }).addTo(map)
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
          maxZoom: 19,
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        }).on('tileerror', () => { if (!disposed) setTileFailed(true) }).addTo(map)
        for (const group of groups) {
          const icon = buildingIcon()
          if (group.records.length > 1) {
            const count = document.createElement('span')
            count.className = 'city-map-count'
            count.textContent = String(group.records.length)
            icon.append(count)
          }
          const label = `${group.records.map(record => record.name).join('; ')}${group.records.length > 1 ? ` · ЖК на этой точке: ${group.records.length}` : ''}`
          const marker = L.marker(group.point, {
            title: label, alt: label,
            icon: L.divIcon({ className: 'city-map-marker', iconSize: [64, 84], iconAnchor: [30, 78], popupAnchor: [0, -64], html: icon }),
          })
          marker.on('add', () => marker.getElement()?.setAttribute('aria-label', label)).addTo(map)
          // Keep the selected card inside the small map, including at 320 px.
          // Auto-pan moves only Leaflet's viewport, never the document.
          marker.bindPopup(buildingPopup(group.records), {
            autoPan: true, autoPanPadding: [12, 12], minWidth: 120, maxWidth: 180, maxHeight: 140,
          })
        }
        map.fitBounds(groups.map(group => group.point), { paddingTopLeft: [40, 90], paddingBottomRight: [40, 35], maxZoom: 14, animate: false })
        if (typeof ResizeObserver !== 'undefined') {
          observer = new ResizeObserver(() => map?.invalidateSize({ pan: false }))
          observer.observe(container.current)
        }
        setState('ready')
      } catch {
        if (!disposed) { map?.remove(); map = undefined; setState('failed') }
      }
    }
    void initialize()
    return () => { disposed = true; observer?.disconnect(); map?.remove() }
  }, [groups, attempt])

  return <>
    {state === 'loading' && <p role="status">Загружаем карту города…</p>}
    {state === 'failed' && <div role="status"><p>Карта города недоступна. Карточки ЖК доступны в таблице реестра.</p>
      <Button variant="outline" onClick={() => setAttempt(value => value + 1)}>Повторить загрузку карты</Button></div>}
    {tileFailed && <p role="status">Не удалось загрузить часть подложки OpenStreetMap. Здания можно выбрать, карточки также доступны в таблице реестра.</p>}
    <div ref={container} className="city-map-canvas" role="region" aria-label="Карта города с условными зданиями" aria-busy={state === 'loading'} />
    <p className="city-map-caption">Tab — выбор здания, Enter — сведения и ссылка на карточку. Карту можно перемещать; масштаб — кнопками +/−. Колесо мыши прокручивает страницу.</p>
  </>
}

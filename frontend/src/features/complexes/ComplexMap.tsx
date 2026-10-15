import { useEffect, useMemo, useRef, useState } from 'react'
import type { Complex } from '@/lib/types'
import 'leaflet/dist/leaflet.css'

type MapRecord = Pick<Complex, 'id' | 'name' | 'city' | 'coordinates' | 'risk' | 'demo'>
const zoneLabels = { GREEN: 'Низкий приоритет', YELLOW: 'Требует проверки', RED: 'Высокий приоритет' }

export function ComplexMap({ complexes }: { complexes: MapRecord[] }) {
  const container = useRef<HTMLDivElement>(null)
  const [state, setState] = useState<'loading' | 'ready' | 'failed'>('loading')
  const [tileFailed, setTileFailed] = useState(false)
  const located = useMemo(() => complexes.filter((item) => item.coordinates &&
    Number.isFinite(item.coordinates.latitude) && Number.isFinite(item.coordinates.longitude) &&
    Math.abs(item.coordinates.latitude) <= 90 && Math.abs(item.coordinates.longitude) <= 180), [complexes])

  useEffect(() => {
    if (!container.current || !located.length) return
    let disposed = false
    let map: import('leaflet').Map | undefined
    let observer: ResizeObserver | undefined
    setState('loading'); setTileFailed(false)
    async function initialize() {
      try {
        const L = await import('leaflet')
        if (disposed || !container.current) return
        map = L.map(container.current, { scrollWheelZoom: false, zoomControl: false })
        L.control.zoom({ zoomInTitle: 'Приблизить', zoomOutTitle: 'Отдалить' }).addTo(map)
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
          maxZoom: 19,
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        }).on('tileerror', () => { if (!disposed) setTileFailed(true) }).addTo(map)
        const bounds: [number, number][] = []
        for (const item of located) {
          const point: [number, number] = [item.coordinates!.latitude, item.coordinates!.longitude]
          bounds.push(point)
          const label = `${item.name}: ${item.risk.score}, ${zoneLabels[item.risk.zone]}`
          const pin = document.createElement('span')
          pin.className = `map-pin map-pin-${item.risk.zone.toLowerCase()}`
          pin.textContent = String(item.risk.score)
          const marker = L.marker(point, {
            title: label, alt: label,
            icon: L.divIcon({ className: 'complex-map-marker', iconSize: [38, 38], iconAnchor: [19, 19],
              html: pin }),
          })
          marker.on('add', () => marker.getElement()?.setAttribute('aria-label', label)).addTo(map)
          // Source names are untrusted data: never interpolate them into popup HTML.
          const popup = document.createElement('div')
          const title = document.createElement('strong')
          title.textContent = item.name
          const detail = document.createElement('p')
          detail.textContent = `${item.city} · ${zoneLabels[item.risk.zone]} · ${item.risk.score}`
          const link = document.createElement('a')
          link.href = `/complexes/${encodeURIComponent(item.id)}`
          link.textContent = 'Открыть карточку'
          popup.append(title, detail, link)
          marker.bindPopup(popup)
        }
        map.fitBounds(bounds, { padding: [32, 32], maxZoom: 13 })
        if (typeof ResizeObserver !== 'undefined') {
          observer = new ResizeObserver(() => map?.invalidateSize())
          observer.observe(container.current)
        }
        setState('ready')
      } catch {
        if (!disposed) setState('failed')
      }
    }
    void initialize()
    return () => { disposed = true; observer?.disconnect(); map?.remove() }
  }, [located])

  if (!located.length) return <p className="inline-notice" role="status">В этой выборке нет объектов с координатами. Откройте карточки из списка ниже.</p>
  return <div className="complex-map-section">
    <p className="map-caption">На карте: {located.length} из {complexes.length} объектов текущей страницы.
      {complexes.some((item) => item.demo) && ' DEMO-координаты условные и не указывают на реальные стройки.'}</p>
    {state === 'loading' && <p role="status" className="map-caption">Загружаем карту…</p>}
    {(state === 'failed' || tileFailed) && <p role="status" className="inline-notice">{state === 'failed' ? 'Карта недоступна.' : 'Не удалось загрузить часть подложки OpenStreetMap.'} Все объекты доступны в списке ниже.</p>}
    <div ref={container} className={`complex-map ${state === 'failed' ? 'hidden' : ''}`} role="region" aria-label="Карта жилых комплексов ВКО" />
    <p className="map-caption">Метки показывают балл с сервера. Tab — выбор метки, Enter — сведения об объекте. Масштаб меняется кнопками +/−.</p>
  </div>
}

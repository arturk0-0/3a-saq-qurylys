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
        const groups = new Map<string, MapRecord[]>()
        for (const item of located) {
          const key = `${item.coordinates!.latitude},${item.coordinates!.longitude}`
          groups.set(key, [...(groups.get(key) || []), item])
        }
        for (const records of groups.values()) {
          records.sort((a, b) => b.risk.score - a.risk.score || a.id.localeCompare(b.id))
          const item = records[0]
          const point: [number, number] = [item.coordinates!.latitude, item.coordinates!.longitude]
          bounds.push(point)
          const label = `${item.name}: ${item.risk.score}, ${zoneLabels[item.risk.zone]}${records.length > 1 ? `; объектов на метке: ${records.length}` : ''}`
          const pin = document.createElement('span')
          pin.className = `map-pin map-pin-${item.risk.zone.toLowerCase()}`
          pin.textContent = String(item.risk.score)
          if (records.length > 1) {
            const count = document.createElement('small')
            count.className = 'map-pin-count'
            count.textContent = String(records.length)
            pin.append(count)
          }
          const marker = L.marker(point, {
            title: label, alt: label, zIndexOffset: item.risk.score * 10,
            icon: L.divIcon({ className: 'complex-map-marker', iconSize: [38, 38], iconAnchor: [19, 19],
              html: pin }),
          })
          marker.on('add', () => marker.getElement()?.setAttribute('aria-label', label)).addTo(map)
          // Source names are untrusted data: never interpolate them into popup HTML.
          const popup = document.createElement('div')
          for (const record of records) {
            const section = document.createElement('section')
            const title = document.createElement('strong')
            title.textContent = record.name
            const detail = document.createElement('p')
            detail.textContent = `${record.city} · ${zoneLabels[record.risk.zone]} · ${record.risk.score}`
            const link = document.createElement('a')
            link.href = `/complexes/${encodeURIComponent(record.id)}`
            link.textContent = 'Открыть карточку'
            if (records.length > 1) link.setAttribute('aria-label', `Открыть карточку: ${record.name}`)
            section.append(title, detail, link)
            popup.append(section)
          }
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
      {complexes.some((item) => item.demo) && ' Координаты учебных объектов условные.'}</p>
    {state === 'loading' && <p role="status" className="map-caption">Загружаем карту…</p>}
    {(state === 'failed' || tileFailed) && <p role="status" className="inline-notice">{state === 'failed' ? 'Карта недоступна.' : 'Не удалось загрузить часть подложки OpenStreetMap.'} Все объекты доступны в списке ниже.</p>}
    <div ref={container} className={`complex-map ${state === 'failed' ? 'hidden' : ''}`} role="region" aria-label="Карта жилых комплексов ВКО" />
    <p className="map-caption">На общей точке показан наибольший балл и число ЖК; все карточки доступны в метке. Tab — выбор метки, Enter — сведения. Масштаб меняется кнопками +/−.</p>
  </div>
}

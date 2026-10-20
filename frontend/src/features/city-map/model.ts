import type { Complex } from '@/lib/types'

export type CityMapRecord = Pick<Complex, 'id' | 'name' | 'address' | 'city' | 'stage' | 'coordinates' | 'demo'>
export const defaultCity = 'Усть-Каменогорск'

export function hasCoordinates(record: CityMapRecord): boolean {
  const point = record.coordinates
  return Boolean(point && Number.isFinite(point.latitude) && Number.isFinite(point.longitude)
    && Math.abs(point.latitude) <= 90 && Math.abs(point.longitude) <= 180)
}

export function citySelection(records: CityMapRecord[], city: string) {
  const construction = records.filter(record => record.city === city && record.stage === 'under_construction')
  const located = construction.filter(hasCoordinates)
  const groups = new Map<string, { point: [number, number]; records: CityMapRecord[] }>()
  for (const record of located) {
    const { latitude, longitude } = record.coordinates!
    const key = `${latitude},${longitude}`
    const group = groups.get(key) || { point: [latitude, longitude], records: [] }
    group.records.push(record)
    groups.set(key, group)
  }
  return { construction, located, missing: construction.length - located.length, groups: [...groups.values()] }
}

// Identical schematic geometry for every object. It does not encode actual
// height, footprint, construction progress, or legal risk.
export const buildingFaces = [
  { points: '8,18 36,4 58,16 30,30', fill: '#dce9f2' },
  { points: '8,18 30,30 30,78 8,66', fill: '#48647c' },
  { points: '30,30 58,16 58,64 30,78', fill: '#88a8bf' },
] as const

export function buildingIcon(): HTMLElement {
  const wrapper = document.createElement('div')
  wrapper.className = 'city-map-building'
  const ns = 'http://www.w3.org/2000/svg'
  const svg = document.createElementNS(ns, 'svg')
  svg.setAttribute('viewBox', '0 0 64 84')
  svg.setAttribute('aria-hidden', 'true')
  for (const face of buildingFaces) {
    const polygon = document.createElementNS(ns, 'polygon')
    polygon.setAttribute('points', face.points)
    polygon.setAttribute('fill', face.fill)
    polygon.setAttribute('stroke', '#29465f')
    polygon.setAttribute('stroke-width', '1')
    svg.append(polygon)
  }
  // Perspective-aligned windows make the three faces readable at marker size.
  for (let row = 0; row < 4; row++) {
    for (let column = 0; column < 3; column++) {
      const x = 34 + column * 8
      const y = 32 + row * 10 - column * 4
      const window = document.createElementNS(ns, 'polygon')
      window.setAttribute('points', `${x},${y} ${x + 4},${y - 2} ${x + 4},${y + 4} ${x},${y + 6}`)
      window.setAttribute('fill', '#eff7fb')
      svg.append(window)
    }
  }
  wrapper.append(svg)
  return wrapper
}

export function buildingPopup(records: CityMapRecord[]): HTMLElement {
  const popup = document.createElement('div')
  popup.className = 'city-map-popup'
  for (const record of records) {
    const section = document.createElement('section')
    const name = document.createElement('strong')
    name.textContent = record.name
    const address = document.createElement('p')
    address.textContent = record.address || 'Адрес не указан'
    const link = document.createElement('a')
    link.href = `/complexes/${encodeURIComponent(record.id)}`
    link.textContent = 'Открыть карточку ЖК'
    link.setAttribute('aria-label', `Открыть карточку ЖК: ${record.name}`)
    section.append(name, address)
    if (record.demo) {
      const demo = document.createElement('p')
      demo.textContent = 'DEMO · условные координаты'
      section.append(demo)
    }
    section.append(link)
    popup.append(section)
  }
  return popup
}

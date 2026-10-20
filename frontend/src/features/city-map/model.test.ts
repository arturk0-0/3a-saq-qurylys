import { expect, it } from 'vitest'
import { buildingFaces, buildingIcon, buildingPopup, citySelection, defaultCity, type CityMapRecord } from './model'

export const record: CityMapRecord = { id: 'a', name: 'DEMO — Дом', city: defaultCity, address: 'Учебный адрес',
  stage: 'under_construction', demo: true, coordinates: { latitude: 49.95, longitude: 82.61 } }

it('selects only the requested city and known construction stage, retaining missing coordinates in the count', () => {
  const records = [record, { ...record, id: 'no-point', coordinates: null },
    { ...record, id: 'ready', stage: 'commissioned' as const }, { ...record, id: 'planned', stage: 'planning' as const },
    { ...record, id: 'unknown', stage: undefined as unknown as CityMapRecord['stage'] }, { ...record, id: 'other-city', city: 'Риддер' }]
  const result = citySelection(records, defaultCity)
  expect(result.construction.map(item => item.id)).toEqual(['a', 'no-point'])
  expect(result.located).toEqual([record])
  expect(result.missing).toBe(1)
  expect(citySelection(records, 'Риддер').located[0].id).toBe('other-city')
})

it('rejects non-finite/out-of-range coordinates and accepts actual zero coordinates without replacing them', () => {
  const values = [null, { latitude: NaN, longitude: 82 }, { latitude: 49, longitude: Infinity },
    { latitude: 90.1, longitude: 0 }, { latitude: 0, longitude: -180.1 }, { latitude: 0, longitude: 0 }]
  const result = citySelection(values.map((coordinates, index) => ({ ...record, id: String(index), coordinates })), defaultCity)
  expect(result.missing).toBe(5)
  expect(result.groups[0].point).toEqual([0, 0])
})

it('groups identical positions without moving them or mutating source records', () => {
  const records = [record, { ...record, id: 'b' }, { ...record, id: 'c', coordinates: { latitude: 49.96, longitude: 82.61 } }]
  const before = JSON.stringify(records)
  const result = citySelection(records, defaultCity)
  expect(result.groups).toHaveLength(2)
  expect(result.groups[0]).toEqual({ point: [49.95, 82.61], records: records.slice(0, 2) })
  expect(result.located).toHaveLength(3)
  expect(JSON.stringify(records)).toBe(before)
})

it('creates three distinct perspective faces and identical model geometry for all buildings', () => {
  const first = buildingIcon()
  const second = buildingIcon()
  expect(first).not.toBe(second)
  expect(first.outerHTML).toBe(second.outerHTML)
  expect(new Set(buildingFaces.map(face => face.points)).size).toBe(3)
  expect(new Set(buildingFaces.map(face => face.fill)).size).toBe(3)
  expect(first.querySelectorAll('polygon')).toHaveLength(15)
  expect(first.querySelector('svg')).toHaveAttribute('viewBox', '0 0 64 84')
})

it('renders untrusted name/address as text, encodes IDs, and marks DEMO per object', () => {
  const popup = buildingPopup([{ ...record, id: 'a/b?x=1', name: '<img src=x onerror=alert(1)>', address: '<script>bad()</script>' },
    { ...record, id: 'real', name: 'Реальный источник', demo: false, address: '' }])
  expect(popup.querySelectorAll('section')).toHaveLength(2)
  expect(popup.querySelector('img, script')).toBeNull()
  expect(popup.textContent).toContain('<script>bad()</script>')
  expect(popup.querySelector('a')).toHaveAttribute('href', '/complexes/a%2Fb%3Fx%3D1')
  expect(popup.querySelectorAll('section')[1].textContent).toContain('Адрес не указан')
  expect(popup.querySelectorAll('section')[1].textContent).not.toContain('DEMO')
})

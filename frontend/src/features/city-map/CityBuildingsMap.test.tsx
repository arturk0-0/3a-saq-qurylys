import { StrictMode } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { CityBuildingsMap } from './CityBuildingsMap'
import { citySelection, defaultCity, type CityMapRecord } from './model'

const record: CityMapRecord = { id: 'a', name: 'DEMO — Дом', city: defaultCity, address: 'Условная улица, 1',
  stage: 'under_construction', demo: true, coordinates: { latitude: 49.95, longitude: 82.61 } }
const groups = (items: CityMapRecord[]) => citySelection(items, defaultCity).groups

it('survives StrictMode, tile failure and changed records; releases observers and the Leaflet container', async () => {
  const disconnected = vi.fn()
  vi.stubGlobal('ResizeObserver', class { observe = vi.fn(); disconnect = disconnected })
  const view = render(<StrictMode><CityBuildingsMap groups={groups([record])} /></StrictMode>)
  const marker = await screen.findByRole('button', { name: record.name })
  fireEvent.click(marker)
  expect(screen.getByText(record.address)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: `Открыть карточку ЖК: ${record.name}` })).toHaveAttribute('href', '/complexes/a')
  const tile = view.container.querySelector('.leaflet-tile')
  expect(tile).not.toBeNull()
  fireEvent.error(tile!)
  expect(screen.getByRole('status')).toHaveTextContent('Не удалось загрузить часть подложки')
  view.rerender(<StrictMode><CityBuildingsMap groups={groups([{ ...record, id: 'b', name: 'Другой ЖК' }])} /></StrictMode>)
  await screen.findByRole('button', { name: 'Другой ЖК' })
  expect(screen.queryByRole('button', { name: record.name })).not.toBeInTheDocument()
  expect(disconnected).toHaveBeenCalledTimes(1)
  const canvas = view.container.querySelector('.city-map-canvas') as HTMLElement & { _leaflet_id?: number }
  view.unmount()
  expect(disconnected).toHaveBeenCalledTimes(2)
  expect(canvas._leaflet_id).toBeUndefined()
})

it('offers each colocated complex separately and keeps the same building geometry across points', async () => {
  const view = render(<CityBuildingsMap groups={groups([record, { ...record, id: 'b', name: 'Второй ЖК' },
    { ...record, id: 'c', name: 'Третий ЖК', coordinates: { latitude: 49.96, longitude: 82.62 } }])} />)
  const shared = await screen.findByRole('button', { name: /ЖК на этой точке: 2/ })
  expect(view.container.querySelectorAll('.leaflet-marker-icon')).toHaveLength(2)
  const icons = view.container.querySelectorAll('.city-map-building svg')
  expect(icons[0].outerHTML).toBe(icons[1].outerHTML)
  fireEvent.click(shared)
  expect(screen.getByRole('link', { name: `Открыть карточку ЖК: ${record.name}` })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Открыть карточку ЖК: Второй ЖК' })).toHaveAttribute('href', '/complexes/b')
  await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument())
})

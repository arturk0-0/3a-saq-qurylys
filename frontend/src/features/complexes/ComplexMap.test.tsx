import { StrictMode } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, it } from 'vitest'
import { ComplexMap } from './ComplexMap'

const record = { id: 'demo-a', name: '<img src=x onerror=alert(1)>', city: 'Риддер', demo: true,
  coordinates: { latitude: 50.34, longitude: 83.51 }, risk: { score: 35, zone: 'YELLOW', factors: [] } } satisfies Parameters<typeof ComplexMap>[0]['complexes'][number]

it('keeps the list fallback when no valid coordinates are available', () => {
  render(<ComplexMap complexes={[{ ...record, coordinates: null }, { ...record, coordinates: { latitude: NaN, longitude: 83 } }]} />)
  expect(screen.getByRole('status')).toHaveTextContent('нет объектов с координатами')
  expect(screen.queryByRole('region')).not.toBeInTheDocument()
})

it('shows the server score, escapes source names, and survives tile outages and remounts', async () => {
  const { container, rerender } = render(<StrictMode><ComplexMap complexes={[record]} /></StrictMode>)
  const marker = await screen.findByRole('button', { name: `${record.name}: 35, Требует проверки` })
  expect(marker).toHaveTextContent('35')
  fireEvent.click(marker)
  expect(screen.getByText(record.name)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Открыть карточку' })).toHaveAttribute('href', '/complexes/demo-a')
  expect(container.querySelector('.leaflet-popup-content img')).toBeNull()
  expect(screen.getByText(/Координаты учебных объектов условные/)).toBeInTheDocument()
  const tile = container.querySelector<HTMLImageElement>('.leaflet-tile')
  expect(tile).not.toBeNull()
  fireEvent.error(tile!)
  expect(screen.getByRole('status')).toHaveTextContent('Все объекты доступны в списке ниже')
  rerender(<StrictMode><ComplexMap complexes={[{ ...record, id: 'demo-b', risk: { score: 70, zone: 'RED', factors: [] } }]} /></StrictMode>)
  await waitFor(() => expect(screen.getByRole('button', { name: `${record.name}: 70, Высокий приоритет` })).toBeInTheDocument())
  expect(screen.queryByRole('button', { name: `${record.name}: 35, Требует проверки` })).not.toBeInTheDocument()
})

it('keeps a high-priority complex visible when multiple records share coordinates', async () => {
  const high = { ...record, id: 'high', name: 'DEMO — Приоритетный', risk: { score: 70, zone: 'RED' as const, factors: [] } }
  render(<ComplexMap complexes={[record, high]} />)
  const marker = await screen.findByRole('button', { name: /DEMO — Приоритетный: 70.*объектов на метке: 2/ })
  expect(document.querySelectorAll('.leaflet-marker-icon')).toHaveLength(1)
  expect(marker.querySelector('.map-pin')).toHaveClass('map-pin-red')
  fireEvent.click(marker)
  expect(screen.getByRole('link', { name: `Открыть карточку: ${record.name}` })).toHaveAttribute('href', '/complexes/demo-a')
  expect(screen.getByRole('link', { name: `Открыть карточку: ${high.name}` })).toHaveAttribute('href', '/complexes/high')
})

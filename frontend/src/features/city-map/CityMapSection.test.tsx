import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { CityMapSection } from './CityMapSection'
import { defaultCity, type CityMapRecord } from './model'

const record: CityMapRecord = { id: 'a', name: 'DEMO — Дом', city: defaultCity, address: 'Условный адрес',
  stage: 'under_construction', demo: true, coordinates: { latitude: 49.95, longitude: 82.61 } }

it('starts closed, opens only eligible buildings, reports partial coverage and removes the map on collapse', async () => {
  const view = render(<CityMapSection complexes={[record, { ...record, id: 'b', coordinates: null }]} loading={false} failed={false} catalogLimited />)
  const trigger = screen.getByRole('button', { name: 'Показать карту города' })
  expect(trigger).toHaveAttribute('aria-expanded', 'false')
  expect(screen.queryByRole('region', { name: 'Карта города с условными зданиями' })).not.toBeInTheDocument()
  fireEvent.click(trigger)
  expect(screen.getByLabelText('Город на карте')).toHaveValue(defaultCity)
  await screen.findByRole('button', { name: record.name })
  expect(screen.getByText(/На карте: 1 из 2/)).toHaveTextContent('это не все ЖК города')
  expect(screen.getByText(/Каталог ограничен/)).toBeInTheDocument()
  expect(screen.getByText(/Без корректных координат: 1/)).toBeInTheDocument()
  expect(screen.getByText(/DEMO: координаты/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Скрыть карту города' }))
  expect(view.container.querySelector('.leaflet-container')).toBeNull()
})

it('handles refresh/error/empty and city selection without labeling unknown stages as construction', () => {
  const records = [{ ...record, stage: undefined as unknown as CityMapRecord['stage'] }, { ...record, city: 'Риддер', coordinates: null }]
  const view = render(<CityMapSection complexes={records} loading failed={false} />)
  fireEvent.click(screen.getByRole('button', { name: 'Показать карту города' }))
  expect(screen.getByRole('status')).toHaveTextContent('Обновляем выборку')
  view.rerender(<CityMapSection complexes={records} loading={false} failed />)
  expect(screen.getByRole('status')).toHaveTextContent('Не удалось получить выборку')
  view.rerender(<CityMapSection complexes={records} loading={false} failed={false} />)
  expect(screen.getByText(/На карте: 0 из 0/)).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Город на карте'), { target: { value: 'Риддер' } })
  expect(screen.getByText(/На карте: 0 из 1/)).toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('Нет объектов для карты')
})

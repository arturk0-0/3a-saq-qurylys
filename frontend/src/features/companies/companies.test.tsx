import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { AuthContext } from '@/features/auth/AuthProvider'
import { ApiError, type ApiClient } from '@/lib/http'
import { CompanyDetail } from './CompanyDetail'
import { CompaniesPage } from './CompaniesPage'
import { CitationLink } from './CitationLink'
import { ProjectParties } from './ProjectParties'
import type { Company, Preview } from './types'
import type { Complex } from '@/lib/types'

const source = { publisher: 'Homeportal · КЖК', url: 'https://homeportal.kz/ru/projects/12', retrievedAt: '2026-10-19T10:00:00Z', effectiveDate: null, responseSha256: 'a'.repeat(64) }
const project = { recordId: '12', name: 'Учебный берег', city: 'Усть-Каменогорск', address: 'Учебный адрес',
  source, stage: 'under_construction', stageSource: source, coordinateStatus: 'outside_city', coordinates: null,
  commissioningReference: null, commissioningDate: null, documentSha256: 'b'.repeat(64),
  parties: [{ role: 'developer', bin: '000000000001', name: 'Учебный застройщик', website: null },
    { role: 'authorized_company', bin: '000000000002', name: 'Учебный получатель', website: null }] } as Preview['project']
const profile: Company = { id: 'bin-000000000001', name: 'Учебная компания', bin: '000000000001', demo: false, version: 1,
  facts: [{ field: 'name', value: 'Учебная компания', source, status: 'source_reported' },
    { field: 'name', value: 'Другое имя из источника', source: { ...source, url: 'https://homeportal.kz/ru/projects/13' }, status: 'source_reported' }],
  projects: [project], updatedAt: source.retrievedAt, lastError: null, foundCompletedCount: null, coverage: 'saved_source_projects_only' }
function setup(node: React.ReactNode, api: ApiClient, path = '/companies') {
  return render(<AuthContext.Provider value={{ status: 'authenticated', profile: null, error: null, api,
    signIn: vi.fn(), logout: vi.fn() }}><MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/companies" element={node} /><Route path="/companies/:id" element={node} />
  </Routes></MemoryRouter></AuthContext.Provider>)
}
it('shows attributed conflicting values and unknown registration/count without inventing zero or current freshness', async () => {
  const api = vi.fn(async (_path: string, _init?: RequestInit) => profile)
  setup(<CompanyDetail />, api as ApiClient, '/companies/bin-000000000001')
  expect(await screen.findByRole('heading', { name: 'Организация · БИН 000000000001' })).toBeInTheDocument()
  expect(screen.getByText(/В сохранённых источниках есть различающиеся сведения/)).toBeInTheDocument()
  expect(screen.getByText('Количество завершённых объектов не установлено.')).toBeInTheDocument()
  expect(screen.getAllByText('Сведения пока не найдены')).toHaveLength(4)
  const citations = screen.getAllByRole('link', { name: /Homeportal/ })
  expect(citations[0]).toHaveAttribute('href', source.url)
  expect(citations[0]).toHaveAttribute('rel', 'noopener noreferrer')
  expect(citations[0]).toHaveAttribute('title', expect.stringContaining('дата сведений не указана'))
  expect(api.mock.calls.every(([, init]) => !init?.method)).toBe(true)
})
it('retains the saved facts when refresh fails and offers explicit reload', async () => {
  const api = vi.fn(async (_path: string, init?: RequestInit) => {
    if (init?.method) throw new ApiError(409, 'CONFLICT', 'Данные изменились')
    return profile
  })
  setup(<CompanyDetail />, api as ApiClient, '/companies/bin-000000000001')
  fireEvent.click(await screen.findByRole('button', { name: 'Обновить по источникам' }))
  await screen.findByText('Данные изменились')
  expect(screen.getByText('Другое имя из источника')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Загрузить сохранённую версию' })).toBeInTheDocument()
  expect(JSON.parse(String(api.mock.calls.find(([, init]) => init?.method)?.[1]?.body))).toEqual({ expectedVersion: 1 })
})
it('search/preview/save requires explicit action and cannot import real data into demo registry', async () => {
  const api = vi.fn(async (path: string, init?: RequestInit) => {
    if (init?.method) return { companyIds: ['bin-000000000001', 'bin-000000000002'], registryId: null }
    if (path.includes('/search?')) return { items: [{ recordId: '12', name: project.name, address: project.address, developer: 'Учебный застройщик', holder: 'Учебный получатель' }], limited: false }
    if (path.endsWith('/company-projects/12')) return { project, savedVersion: 0, canImportToRegistry: false }
    return { items: [], nextCursor: null }
  })
  setup(<CompaniesPage />, api as ApiClient)
  await screen.findByText(/Организации пока не сохранены/)
  expect(api.mock.calls.every(([path]) => !path.includes('/company-projects'))).toBe(true)
  fireEvent.change(screen.getByLabelText('Название ЖК или адрес'), { target: { value: 'Учебный берег' } })
  fireEvent.click(screen.getByRole('button', { name: 'Найти в Homeportal' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Посмотреть участников' }))
  expect(await screen.findByText('Юридический застройщик')).toBeInTheDocument()
  expect(screen.getByRole('checkbox')).toBeDisabled()
  expect(screen.getByText(/Достоверная точка объекта не установлена/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить участников' }))
  await screen.findByRole('status')
  await waitFor(() => expect(screen.getAllByRole('link', { name: /Открыть организацию/ })).toHaveLength(2))
  const writes = api.mock.calls.filter(([, init]) => init?.method)
  expect(writes).toHaveLength(1)
  expect(JSON.parse(String(writes[0][1]?.body))).toEqual({ expectedVersion: 0, expectedDocumentSha256: 'b'.repeat(64), importToRegistry: false })
})
it('uses separate participant links and preserves unknown authorized company in historical cards', () => {
  const complex = { developer: { id: 'demo-developer-01', name: 'Учебный застройщик', bin: '000000000001', demo: true }, authorizedCompany: null } as Complex
  setup(<ProjectParties complex_={complex} />, vi.fn() as ApiClient)
  expect(screen.getByRole('link', { name: 'Учебный застройщик →' })).toHaveAttribute('href', '/companies/demo-developer-01')
  expect(screen.getByText('Сведения пока не найдены')).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: /Homeportal/ })).not.toBeInTheDocument()
})
it('never renders a non-web source as an executable link', () => {
  const result = render(<CitationLink source={{ ...source, url: 'javascript:alert(1)' }} />)
  expect(result.container.querySelector('a')).toBeNull()
})

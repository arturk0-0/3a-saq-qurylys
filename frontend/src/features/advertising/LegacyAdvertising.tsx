import { Link, Navigate, useLocation, useParams } from 'react-router-dom'
import { ErrorState, LoadingState, PageHeading } from '@/components/WorkspaceUI'
import { AdvertisementDetail } from '@/features/advertisements/AdvertisementsPage'
import { FindingDetail } from '@/features/monitoring/FindingDetail'
import { useApiQuery } from '@/lib/useApiQuery'
import type { MonitorStatus } from '@/features/monitoring/types'
import { legacyTarget } from './filters'
import './advertising.css'
import '@/features/monitoring/monitoring.css'

export function LegacyAdvertisingRedirect({ kind }: { kind: 'monitoring' | 'advertisement' }) {
  const { id } = useParams()
  const { search } = useLocation()
  const target = legacyTarget(kind, id, search)
  const selected = id || new URLSearchParams(search).get('item')
  return target.startsWith('/advertising/legacy/') && selected
    ? <ResolveLegacyMaterial key={`${kind}:${selected}`} legacyId={selected} fallback={target} search={search} />
    : <Navigate replace to={target} />
}

function ResolveLegacyMaterial({ legacyId, fallback, search }: { legacyId: string; fallback: string; search: string }) {
  const material = useApiQuery<{ id: string }>(`/api/v1/materials/${encodeURIComponent(legacyId)}`)
  if (material.data?.id) return <Navigate replace to={`/advertising/materials/${encodeURIComponent(material.data.id)}${search}`} />
  return <div className="advertising ad-stack">
    {material.loading ? <LoadingState /> : <ErrorState message={material.error || 'Материал пока недоступен.'} retry={material.refresh} />}
    <Link className="detail-link" to={fallback}>Открыть сохранённый оригинал и прежнюю историю →</Link>
  </div>
}

// Explicit archive links keep original files and historical actions available.
export function LegacyAdvertising({ kind }: { kind: 'monitoring' | 'advertisement' }) {
  const { id } = useParams()
  const { search } = useLocation()
  const status = useApiQuery<MonitorStatus>(kind === 'monitoring' ? '/api/v1/monitoring/status' : null)
  return <div className="advertising"><Link className="back-link" to={'/advertising' + search}>← Реклама · все материалы</Link>
    {id && <Link className="detail-link" to={kind === 'advertisement' ? `/advertisements/${encodeURIComponent(id)}${search}` : `/monitoring?item=${encodeURIComponent(id)}`}>Перейти к единой проверке материала →</Link>}
    <PageHeading eyebrow="Сохранённая ссылка" title="Оригинал и прежняя история" description="Оригинальные файлы, документы и решения по старой ссылке сохранены. Единая проверка доступна в разделе «Все материалы»." />
    {kind === 'advertisement' ? <AdvertisementDetail /> : id && <div className="monitoring"><FindingDetail key={id} id={id} liveRegistry={Boolean(status.data?.liveRegistryEnabled)} changed={status.refresh} /></div>}
  </div>
}

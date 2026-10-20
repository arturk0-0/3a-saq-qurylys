import { Link, Navigate, useLocation, useParams } from 'react-router-dom'
import { PageHeading } from '@/components/WorkspaceUI'
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
  return <Navigate replace to={legacyTarget(kind, id, search)} />
}

// The agreed facade has no legacy-ID resolver yet. Keep the exact original and
// its historical actions reachable rather than guessing a new material ID.
export function LegacyAdvertising({ kind }: { kind: 'monitoring' | 'advertisement' }) {
  const { id } = useParams()
  const { search } = useLocation()
  const status = useApiQuery<MonitorStatus>(kind === 'monitoring' ? '/api/v1/monitoring/status' : null)
  return <div className="advertising"><Link className="back-link" to={'/advertising' + search}>← Реклама · все материалы</Link>
    <PageHeading eyebrow="Сохранённая ссылка" title="Оригинал и прежняя история" description="Оригинальные файлы, документы и решения по старой ссылке сохранены. Единая проверка доступна в разделе «Все материалы»." />
    {kind === 'advertisement' ? <AdvertisementDetail /> : id && <div className="monitoring"><FindingDetail key={id} id={id} liveRegistry={Boolean(status.data?.liveRegistryEnabled)} changed={status.refresh} /></div>}
  </div>
}

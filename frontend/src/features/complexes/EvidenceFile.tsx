import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/WorkspaceUI'
import { useAuth } from '@/features/auth/AuthProvider'
import { errorMessage } from '@/lib/labels'

export function EvidenceFile({ id }: { id: string }) {
  const { api } = useAuth()
  const [url, setUrl] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => () => { if (url) URL.revokeObjectURL(url) }, [url])
  async function open() {
    setBusy(true); setError(null)
    try { setUrl(URL.createObjectURL(await api<Blob>(`/api/v1/evidence/${id}/file`))) }
    catch (error) { setError(errorMessage(error)) } finally { setBusy(false) }
  }
  return <div className="my-3">{url ? <><img src={url} alt="Оригинальный скриншот источника для проверки аналитиком" className="max-h-96 max-w-full rounded-lg border border-border object-contain" /><a className="detail-link mt-2" href={url} download={`evidence-${id}`}>Скачать оригинал</a></> : <Button size="sm" variant="outline" disabled={busy} onClick={open}>{busy ? 'Загрузка…' : 'Открыть скриншот'}</Button>}{error && <ErrorState message={error} />}</div>
}

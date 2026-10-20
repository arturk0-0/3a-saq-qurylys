import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { ErrorState, LoadingState } from '@/components/WorkspaceUI'
import { useApiQuery } from '@/lib/useApiQuery'
import { formatDate } from '@/lib/labels'
import { reviewLabels } from './presentation'
import type { MaterialPage, ReviewState } from './types'

interface Entry {
  id: string; action: string; createdAt: string; reviewerDisplayName: string | null
  details: { notes?: string; disposition?: ReviewState }
}

export function MaterialHistory({ id, version }: { id: string; version: number }) {
  const [open, setOpen] = useState(false)
  const [cursor, setCursor] = useState('')
  const previousVersion = useRef(version)
  const query = useApiQuery<MaterialPage<Entry>>(open ? `/api/v1/materials/${encodeURIComponent(id)}/history?limit=20${cursor ? '&cursor=' + encodeURIComponent(cursor) : ''}` : null)
  useEffect(() => {
    if (previousVersion.current !== version) {
      previousVersion.current = version; setCursor(''); if (open) query.refresh()
    }
  }, [version, open, query.refresh])
  return <details className="panel content-pad ad-panel" open={open} onToggle={event => setOpen(event.currentTarget.open)}><summary>История проверок материала</summary>
    {open && <div className="ad-stack">{query.loading ? <LoadingState /> : query.error ? <ErrorState message={query.error} retry={() => { if (cursor) setCursor(''); else query.refresh() }} />
      : !query.data?.items.length ? <p>Проверок материала пока нет.</p> : query.data.items.map(entry => <article className="history-entry" key={entry.id}>
        <strong>{entry.action.includes('retry') ? 'Повтор анализа' : 'Проверка материала'}</strong>
        <p>{formatDate(entry.createdAt)} · {entry.reviewerDisplayName || 'Аналитик'}</p>
        {entry.details.disposition && <p>{reviewLabels[entry.details.disposition]}</p>}
        {entry.details.notes && <p>{entry.details.notes}</p>}
      </article>)}
      <div className="form-actions">{cursor && <Button variant="outline" onClick={() => setCursor('')}>В начало проверок</Button>}
        {query.data?.nextCursor && !query.loading && <Button variant="outline" onClick={() => setCursor(query.data!.nextCursor!)}>Следующие проверки</Button>}</div>
    </div>}
  </details>
}

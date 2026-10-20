import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { ErrorState, FormField } from '@/components/WorkspaceUI'
import { useApiQuery } from '@/lib/useApiQuery'
import type { Complex, Page } from '@/lib/types'

export function ComplexPicker({ value, onChange, label, disabled, selectedName }: {
  value: string; onChange: (id: string) => void; label: string; disabled?: boolean; selectedName?: string
}) {
  const [draft, setDraft] = useState('')
  const [search, setSearch] = useState('')
  const [cursor, setCursor] = useState('')
  const query = new URLSearchParams({ limit: '20', sort: 'name', q: search })
  if (cursor) query.set('cursor', cursor)
  const result = useApiQuery<Page<Complex>>('/api/v1/complexes?' + query)
  return <div className="ad-stack">
    <FormField label={`Найти ЖК: ${label}`}><input value={draft} disabled={disabled} onChange={event => setDraft(event.target.value)} placeholder="Название или адрес" /></FormField>
    <div className="form-actions"><Button type="button" variant="outline" disabled={disabled} onClick={() => { setSearch(draft); setCursor(''); result.refresh() }}>Найти ЖК</Button>
      {result.data?.nextCursor && <Button type="button" variant="outline" disabled={disabled} onClick={() => setCursor(result.data!.nextCursor!)}>Следующие ЖК</Button>}</div>
    <FormField label={label}><select value={value} disabled={disabled || result.loading || Boolean(result.error)} onChange={event => onChange(event.target.value)}>
      <option value="">Без выбранного ЖК</option>
      {value && !result.data?.items.some(item => item.id === value) && <option value={value}>{selectedName || 'Выбранный ЖК'}</option>}
      {result.data?.items.map(item => <option value={item.id} key={item.id}>{item.name} · {item.address}</option>)}
    </select></FormField>
    {result.error && <ErrorState message={result.error} retry={result.refresh} />}
    {result.data?.nextCursor && <p className="form-hint">Показана часть найденных ЖК. Уточните поиск или откройте следующие.</p>}
  </div>
}

import { useId, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { DemoBadge, EmptyState, ErrorState, FormField, LoadingState, PageHeading, SourceLink } from '@/components/WorkspaceUI'
import { useAuth } from '@/features/auth/AuthProvider'
import { errorMessage, formatDate } from '@/lib/labels'
import { useApiQuery } from '@/lib/useApiQuery'
import type { Advertisement, Complex, Page } from '@/lib/types'
import { AnalysisPanel } from './AnalysisPanel'

export function AdvertisementForm({ complexId, onSaved, onCancel }: { complexId?: string; onSaved: () => void; onCancel: () => void }) {
  const { api } = useAuth()
  const complexes = useApiQuery<Page<Complex>>(complexId ? null : '/api/v1/complexes?limit=100&sort=name')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setBusy(true); setError(null)
    try {
      await api('/api/v1/advertisements', { method: 'POST', body: JSON.stringify({
        complexId: complexId || form.get('complexId'), platform: form.get('platform'), account: form.get('account'),
        sourceUrl: form.get('sourceUrl'), text: form.get('text'), publishedAt: new Date(String(form.get('publishedAt'))).toISOString(),
      }) })
      onSaved()
    } catch (error) { setError(errorMessage(error)) } finally { setBusy(false) }
  }
  return <form className="editor-form" onSubmit={submit}><h2>Новое объявление</h2>
    <p className="form-hint">Сохраните оригинальный текст и ссылку. Оценка факторов выполняется отдельно.</p>
    {!complexId && <><FormField label="Жилой комплекс"><select name="complexId" required defaultValue="" disabled={complexes.loading || Boolean(complexes.error)}><option value="" disabled>{complexes.loading ? 'Загружаем ЖК…' : 'Выберите ЖК'}</option>{complexes.data?.items.map((row) => <option value={row.id} key={row.id}>{row.name}</option>)}</select></FormField>
      {complexes.error && <ErrorState message={complexes.error} retry={complexes.refresh} />}
      {!complexes.loading && !complexes.error && !complexes.data?.items.length && <p className="inline-notice">В реестре нет ЖК. Администратор должен загрузить DEMO-набор.</p>}
      {complexes.data?.nextCursor && <p className="form-hint">Показаны первые 100 ЖК. Нужный объект можно найти в реестре и добавить объявление из его карточки.</p>}</>}
    <div className="form-grid"><FormField label="Площадка"><input name="platform" required maxLength={500} placeholder="Например, Instagram" /></FormField>
      <FormField label="Аккаунт / автор"><input name="account" required maxLength={500} /></FormField></div>
    <FormField label="Оригинальная ссылка"><input name="sourceUrl" type="url" required placeholder="https://…" /></FormField>
    <FormField label="Дата публикации" hint="Введите время в часовом поясе вашего компьютера."><input name="publishedAt" type="datetime-local" required /></FormField>
    <FormField label="Текст объявления"><textarea name="text" required maxLength={20000} rows={5} placeholder="Вставьте текст без изменений" /></FormField>
    {error && <ErrorState message={error} />}
    <div className="form-actions"><Button type="submit" disabled={busy || (!complexId && (complexes.loading || Boolean(complexes.error) || !complexes.data?.items.length))}>{busy ? 'Сохраняем…' : 'Сохранить объявление'}</Button><Button type="button" variant="outline" disabled={busy} onClick={onCancel}>Отмена</Button></div>
  </form>
}

export function AdvertisementCard({ ad }: { ad: Advertisement }) {
  const [analysis, setAnalysis] = useState(false)
  const analysisId = useId()
  return <article className="advertisement-card"><div className="flex flex-wrap items-center justify-between gap-2">
    <div><strong>{ad.platform}</strong><span className="ml-2 text-sm text-muted-foreground">@{ad.account}</span></div>{ad.demo && <DemoBadge />}</div>
    <p className="mt-2 text-xs text-muted-foreground">Опубликовано {formatDate(ad.publishedAt)} · Сохранено {formatDate(ad.capturedAt)}</p>
    <p className="ad-text">{ad.text}</p><div className="flex flex-wrap items-center gap-5"><SourceLink url={ad.sourceUrl} />
      <Link to={`/complexes/${ad.complexId}`} className="detail-link">Открыть ЖК →</Link>
      <Button variant="outline" size="sm" aria-expanded={analysis} aria-controls={analysisId} onClick={() => setAnalysis(!analysis)}>{analysis ? 'Скрыть анализ' : 'Скриншоты и AI-анализ'}</Button></div>
    <div id={analysisId}>{analysis && <AnalysisPanel adId={ad.id} />}</div>
  </article>
}

export function AdvertisementsPage() {
  const [creating, setCreating] = useState(false)
  const [cursor, setCursor] = useState('')
  const { data, loading, error, refresh } = useApiQuery<Page<Advertisement>>(`/api/v1/advertisements?limit=50${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`)
  return <>
    <PageHeading eyebrow="Мониторинг источников" title="Объявления" description="Оригинальные публикации, текст и источники для последующей проверки."
      action={<Button onClick={() => setCreating(true)}><Plus size={16} className="mr-2" />Добавить объявление</Button>} />
    {creating && <section className="panel mb-6"><AdvertisementForm onSaved={() => { setCreating(false); setCursor(''); refresh() }} onCancel={() => setCreating(false)} /></section>}
    {loading ? <LoadingState /> : error ? <ErrorState message={error} retry={refresh} />
      : !data?.items.length ? <EmptyState title="Объявлений пока нет"><p>Добавьте первую публикацию или загрузите DEMO-набор.</p></EmptyState>
      : <div className="space-y-4">{data.items.map((ad) => <AdvertisementCard key={ad.id} ad={ad} />)}</div>}
    {(cursor || data?.nextCursor) && <div className="pagination"><Button variant="outline" onClick={() => setCursor('')}>В начало</Button>{data?.nextCursor && <Button variant="outline" onClick={() => setCursor(data.nextCursor!)}>Далее</Button>}</div>}
  </>
}

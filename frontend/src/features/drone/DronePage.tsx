import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { EmptyState, ErrorState, FormField, LoadingState, PageHeading } from '@/components/WorkspaceUI'
import { useAuth } from '@/features/auth/AuthProvider'
import { useApiQuery } from '@/lib/useApiQuery'
import { errorMessage, formatDate } from '@/lib/labels'
import { safeReference, statusLabels, validPhoto, type Criterion, type Inspection } from './types'
import './drone.css'

export function DronePage() {
  const { api } = useAuth()
  const navigate = useNavigate()
  const [cursor, setCursor] = useState('')
  const list = useApiQuery<{ items: Inspection[]; nextCursor: string | null }>('/api/v1/drone-inspections?limit=20' + (cursor ? '&cursor=' + cursor : ''))
  const defaults = useApiQuery<{ items: Criterion[] }>('/api/v1/drone-inspections/checklist')
  const complexes = useApiQuery<{ items: { id: string; name: string; address: string }[]; catalogLimited?: boolean }>('/api/v1/complexes?limit=100')
  const [criteria, setCriteria] = useState<Criterion[]>([])
  const [title, setTitle] = useState('')
  const [complexId, setComplex] = useState('')
  const [capture, setCapture] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const attempt = useRef<{ id: string; payload: string } | null>(null)
  useEffect(() => { if (defaults.data) setCriteria(defaults.data.items) }, [defaults.data])
  async function submit(event: FormEvent) {
    event.preventDefault(); setError(null)
    if (!file || !validPhoto(file)) { setError('Выберите JPEG, PNG или WebP до 6 МБ.'); return }
    if (!criteria.length || criteria.some(c => !c.label.trim() || (c.sourceUrl && !safeReference(c.sourceUrl)))) { setError('Заполните пункты чек-листа и проверьте ссылки.'); return }
    const capturedAt = capture ? new Date(capture).toISOString() : null
    if (capturedAt && Date.parse(capturedAt) > Date.now()) { setError('Дата съёмки не может быть в будущем.'); return }
    const fields = { title: title.trim(), complexId: complexId || null, capturedAt,
      checklist: criteria.map(c => ({ ...c, label: c.label.trim(), sourceUrl: c.sourceUrl?.trim() || null })) }
    const fingerprint = JSON.stringify(fields)
    if (!attempt.current || attempt.current.payload !== fingerprint) attempt.current = { id: crypto.randomUUID(), payload: fingerprint }
    setBusy(true)
    let created: Inspection | null = null
    try {
      created = await api<Inspection>('/api/v1/drone-inspections', { method: 'POST', body: JSON.stringify({ ...fields, requestId: attempt.current.id }) })
      if (!created.photo) await api('/api/v1/drone-inspections/' + created.id + '/photo?expected_version=' + created.version, { method: 'POST', body: file, headers: { 'Content-Type': file.type } })
      navigate('/drone-inspections/' + created.id)
    } catch (failure) {
      if (created) navigate('/drone-inspections/' + created.id, { state: { uploadError: errorMessage(failure) } })
      else setError(errorMessage(failure))
    } finally { setBusy(false) }
  }
  return <div className="drone-feature">
    <PageHeading eyebrow="Осмотр строительной площадки" title="Дрон-инспекция" description="Снимки с дрона, наблюдения по чек-листу и решение эксперта." />
    <section className="panel"><h2>Новая инспекция</h2>
      <form onSubmit={event => void submit(event)}><fieldset disabled={busy} className="drone-fields">
        <div className="drone-form-grid"><FormField label="Название инспекции"><input required maxLength={500} value={title} onChange={e => setTitle(e.target.value)} placeholder="Например, северная сторона площадки" /></FormField>
          <FormField label="Жилой комплекс" hint="Выбирайте только объект, который действительно снят на фотографии."><select value={complexId} onChange={e => setComplex(e.target.value)}><option value="">Без привязки к ЖК</option>{complexes.data?.items.map(c => <option key={c.id} value={c.id}>{c.name} · {c.address}</option>)}</select></FormField>
          <FormField label="Дата и время съёмки" hint="Необязательно. Укажите известное время; дата загрузки хранится отдельно."><input type="datetime-local" value={capture} onChange={e => setCapture(e.target.value)} /></FormField>
          <FormField label="Фотография с дрона" hint="Один статичный JPEG, PNG или WebP до 6 МБ и 20 мегапикселей."><input type="file" required accept="image/jpeg,image/png,image/webp" onChange={e => setFile(e.target.files?.[0] ?? null)} /></FormField></div>
        {complexes.error && <p className="form-hint">Список ЖК недоступен. Инспекцию можно сохранить без привязки.</p>}
        {complexes.data?.catalogLimited && <p className="form-hint">Показана ограниченная выборка ЖК. Не выбирайте похожий объект вместо нужного.</p>}
        <div className="drone-checklist"><h3>Визуальный чек-лист</h3><p>Отредактируйте признаки, которые нужно рассмотреть на снимке. Пункты ниже — отправная точка для осмотра; они не являются перечнем обязательных строительных норм.</p>
          {defaults.loading && <LoadingState />}{defaults.error && <ErrorState message={defaults.error} retry={defaults.refresh} />}
          {criteria.map((c, index) => <div className="drone-criterion-editor" key={c.id}><FormField label={'Пункт ' + (index + 1)}><input required maxLength={500} value={c.label} onChange={e => setCriteria(rows => rows.map(row => row.id === c.id ? { ...row, label: e.target.value } : row))} /></FormField>
            <details><summary>Ссылка на основание пункта</summary><FormField label={'Источник пункта ' + (index + 1)} hint="Необязательно. Указанный документ автоматически не проверяется."><input type="url" maxLength={2000} value={c.sourceUrl ?? ''} onChange={e => setCriteria(rows => rows.map(row => row.id === c.id ? { ...row, sourceUrl: e.target.value } : row))} /></FormField></details>
            <Button type="button" variant="outline" disabled={criteria.length <= 1} onClick={() => setCriteria(rows => rows.filter(row => row.id !== c.id))} aria-label={'Удалить пункт ' + (index + 1)}>Убрать</Button></div>)}
          <Button type="button" variant="outline" disabled={criteria.length >= 8} onClick={() => setCriteria(rows => [...rows, { id: 'c-' + crypto.randomUUID(), label: '', sourceUrl: null }])}>Добавить пункт</Button>
        </div>{error && <ErrorState message={error} />}<Button type="submit" disabled={!criteria.length}>{busy ? 'Сохраняем фотографию…' : 'Загрузить фотографию'}</Button>
      </fieldset></form>
    </section>
    <section className="panel"><h2>Инспекции</h2>{list.loading ? <LoadingState /> : list.error ? <ErrorState message={list.error} retry={list.refresh} /> : !list.data?.items.length ? <EmptyState title="Фотографий для осмотра пока нет" /> : list.data.items.map(item => <article key={item.id} className="drone-list-row">
      <div><Link className="detail-link" to={'/drone-inspections/' + item.id}>{item.title} →</Link><p>{item.complexName || 'Без привязки к ЖК'} · {formatDate(item.createdAt)}</p></div><span className={'drone-state state-' + item.status}>{statusLabels[item.status]}</span>
    </article>)}{(cursor || list.data?.nextCursor) && <div className="form-actions"><Button variant="outline" onClick={() => setCursor('')}>В начало</Button>{list.data?.nextCursor && <Button variant="outline" onClick={() => setCursor(list.data!.nextCursor!)}>Ещё инспекции</Button>}</div>}</section>
  </div>
}

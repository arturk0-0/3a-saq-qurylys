import { useRef, useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { ErrorState, FormField, LoadingState } from '@/components/WorkspaceUI'
import { useAuth } from '@/features/auth/AuthProvider'
import { ApiError } from '@/lib/http'
import { errorMessage } from '@/lib/labels'
import type { Advertisement } from '@/lib/types'
import { useResource } from './useResource'

export function ScreenshotUpload({ adId, disabled, changed, onBusy }: {
  adId: string; disabled: boolean; changed: () => Promise<unknown>; onBusy: (busy: boolean) => void
}) {
  const { api } = useAuth()
  const ad = useResource<Advertisement>(`/api/v1/advertisements/${encodeURIComponent(adId)}`)
  const fileInput = useRef<HTMLInputElement>(null)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [conflict, setConflict] = useState(false)
  async function upload(event: FormEvent) {
    event.preventDefault()
    if (disabled || busy || !ad.data || conflict) return
    const file = fileInput.current?.files?.[0]
    if (!file?.size) { setError('Выберите непустое изображение.'); return }
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) { setError('Допустимы JPEG, PNG или WebP.'); return }
    if (file.size > 6 * 1024 * 1024) { setError('Максимальный размер — 6 МБ.'); return }
    setBusy(true); onBusy(true); setError(null); setSaved(null)
    try {
      await api(`/api/v1/advertisements/${encodeURIComponent(adId)}/screenshots?expected_version=${ad.data.version}`, { method: 'POST', headers: { 'Content-Type': file.type }, body: file })
      setSaved(`Скриншот «${file.name}» сохранён. Поддерживаемая новая ревизия ожидает автоматического анализа.`)
      await Promise.all([ad.refresh(), changed()])
    } catch (failure) { setError(errorMessage(failure)); if (failure instanceof ApiError && failure.status === 409) setConflict(true) }
    finally { setBusy(false); onBusy(false) }
  }
  return <div className="ad-stack">{ad.loading && <LoadingState />}{ad.error && <ErrorState message={ad.error} retry={() => void ad.refresh().catch(() => {})} />}
    <form className="ad-form" onSubmit={upload}>
      <FormField label="Добавить скриншот к материалу" hint="JPEG, PNG или WebP, до 6 МБ. Подтверждённые решения не заменяются изображением."><input ref={fileInput} type="file" required accept="image/jpeg,image/png,image/webp" disabled={disabled || busy} /></FormField>
      {disabled && !busy && <p className="form-hint">Сначала сохраните текущую проверку: загрузка создаёт новую ревизию.</p>}
      {error && <ErrorState message={error} />}{saved && <p role="status">{saved}</p>}
      {conflict && <Button type="button" variant="outline" onClick={() => { void ad.refresh().then(() => setConflict(false)).catch(() => {}) }}>Обновить версию объявления</Button>}
      <Button disabled={disabled || busy || ad.loading || Boolean(ad.error) || conflict}>Загрузить скриншот</Button>
    </form>
  </div>
}

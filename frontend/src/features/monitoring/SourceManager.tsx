import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { ErrorState, FormField } from '@/components/WorkspaceUI'
import { useAuth } from '@/features/auth/AuthProvider'
import { errorMessage, formatDate } from '@/lib/labels'
import { safeMonitorError, type Source, type Run, type MonitorStatus } from './types'

export function SourceManager({ sources, changed, provider }: { sources: Source[]; changed: () => void; provider?: MonitorStatus | null }) {
  const { api } = useAuth()
  const [kind, setKind] = useState<Source['kind']>('web_search')
  const [target, setTarget] = useState('новостройки квартиры Усть-Каменогорск Риддер')
  const [name, setName] = useState('Поиск жилья ВКО')
  const [interval, setIntervalMinutes] = useState(60)
  const [autoAi, setAutoAi] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<string | null>(null)
  async function add(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null); setResult(null)
    try {
      await api('/api/v1/monitoring/sources', { method: 'POST', body: JSON.stringify({
        name, kind, target, intervalMinutes: interval, autoAnalyze: autoAi,
      }) })
      setResult('Источник сохранён. Он доступен для регулярного сбора.'); changed()
    } catch (failure) { setError(errorMessage(failure)) } finally { setBusy(false) }
  }
  async function action(source: Source, run: boolean, toggleAi = false) {
    setBusy(true); setError(null); setResult(null)
    try {
      if (run) {
        const result = await api<Run>('/api/v1/monitoring/sources/' + source.id + '/run', { method: 'POST' })
        setResult('Сбор завершён: прочитано ' + result.fetched + ', подходит под фильтр ' + result.relevant +
          ', новых ' + result.created + ', повторов ' + result.duplicates +
          (result.autoAiStatus ? '. Авто-AI: ' + (result.autoAiStatus === 'succeeded' ? 'готово' : safeMonitorError(result.autoAiStatus)) : ''))
      } else {
        await api('/api/v1/monitoring/sources/' + source.id, { method: 'PATCH', body: JSON.stringify({
          expectedVersion: source.version, enabled: toggleAi ? source.enabled : !source.enabled,
          autoAnalyze: toggleAi ? !source.autoAnalyze : source.autoAnalyze,
        }) })
        setResult('Настройки источника сохранены.')
      }
    } catch (failure) { setError(errorMessage(failure)) } finally { setBusy(false); changed() }
  }
  return <div className="monitor-sources">
    <section className="panel">
      <h2>Добавить источник сбора</h2>
      <p className="form-hint">Задайте поисковый запрос или публичный Telegram-канал. Ссылки на каждый пост вводить не нужно.</p>
      <form className="editor-form" onSubmit={add}>
        <FormField label="Название источника"><input value={name} maxLength={500} required disabled={busy} onChange={e => setName(e.target.value)} /></FormField>
        <FormField label="Тип источника"><select value={kind} disabled={busy} onChange={e => {
          const value = e.target.value as typeof kind; setKind(value)
          setTarget(value === 'telegram' ? '' : value === 'instagram_ads' ? 'квартиры Өскемен' : 'новостройки квартиры Усть-Каменогорск Риддер')
        }}><option value="web_search">Поиск по интернету — фрагменты выдачи</option><option value="telegram">Публичный Telegram-канал — тексты постов</option><option value="instagram_ads">Instagram — Meta Ad Library через SearchAPI</option></select></FormField>
        {kind === 'instagram_ads' && <p className="inline-notice">Поиск именно рекламы Instagram: Казахстан, активные объявления, тип all. Каждый запуск расходует запрос SearchAPI. Одна страница без автоматических повторов; минимум {provider?.searchApi?.creditReserve ?? 20} запросов сохраняются. Расписание по умолчанию выключено.</p>}
        <FormField label={kind === 'telegram' ? 'Канал Telegram' : 'Поисковый запрос'} hint={kind === 'telegram' ? '@channel или https://t.me/channel. Закрытые каналы не поддерживаются.' : kind === 'instagram_ads' ? 'Например: квартиры Өскемен. Несколько городов лучше искать отдельными источниками. В очередь проходят тексты с признаками ВКО и жилья.' : 'Добавьте город и слова о жилье. Выдача поисковика не является полным текстом рекламы.'}>
          <input value={target} required maxLength={250} disabled={busy} onChange={e => setTarget(e.target.value)} placeholder={kind === 'telegram' ? '@channel' : 'Жильё в ВКО'} />
        </FormField>
        <FormField label="Интервал сбора, минуты" hint="15–1440 минут. Для выполнения интервала нужен включённый серверный worker."><input type="number" min={15} max={1440} value={interval} required disabled={busy} onChange={e => setIntervalMinutes(Number(e.target.value))} /></FormField>
        <label className="monitor-checkbox"><input type="checkbox" checked={autoAi} disabled={busy} onChange={e => setAutoAi(e.target.checked)} /><span>Автоматически анализировать Gemini: платно, максимум одну находку за запуск; действуют общие дневные лимиты.</span></label>
        <Button disabled={busy || !name.trim() || !target.trim()}>{busy ? 'Выполняем…' : 'Сохранить источник'}</Button>
      </form>
    </section>
    {error && <ErrorState message={error} />}
    {result && <p role="status" className="inline-notice">{result}</p>}
    {sources.length === 0 && <section className="panel"><h2>Источники ещё не настроены</h2><p>Сохраните запрос выше, затем запустите первый сбор. Регулярные запуски показываются отдельно.</p></section>}
    {sources.map(source => {
      const running = Boolean(source.leaseUntil && new Date(source.leaseUntil).getTime() > Date.now())
      const waiting = Boolean(source.nextRunAt && new Date(source.nextRunAt).getTime() > Date.now())
      return <section className="panel" key={source.id}>
        <div className="monitor-heading"><h2>{source.name}</h2><span className="monitor-tag">{source.enabled ? 'Источник включён' : 'На паузе'}</span></div>
        <p>{source.kind === 'telegram' ? 'Telegram · @' : source.kind === 'instagram_ads' ? 'Instagram / SearchAPI · ' : 'Интернет-поиск · '}{source.target}</p>
        {source.kind === 'instagram_ads' && <p className="form-hint">{provider?.searchApi?.scheduled ? 'Расписание Instagram разрешено сервером; фактические запуски смотрите в истории.' : 'Только ручной сбор. Расписание Instagram на сервере выключено.'} Дневной лимит: {provider?.searchApi?.dailyLimit ?? 2} попытки.</p>}
        <p className="form-hint">Последний сбор: {formatDate(source.lastRunAt)} · Следующий: {formatDate(source.nextRunAt)} · Интервал {source.intervalMinutes} мин.</p>
        <p>Авто-AI: <strong>{source.autoAnalyze ? 'включён, платные запросы' : 'выключен'}</strong></p>
        {source.lastError && <p className="inline-notice">{safeMonitorError(source.lastError)}</p>}
        <div className="form-actions">
          <Button disabled={busy || !source.enabled || running || waiting} onClick={() => void action(source, true)}>{running ? 'Сбор выполняется…' : waiting ? 'Ожидает своего интервала' : 'Получить публикации'}</Button>
          <Button variant="outline" disabled={busy || running} onClick={() => void action(source, false)}>{source.enabled ? 'Поставить на паузу' : 'Возобновить источник'}</Button>
          <Button variant="outline" disabled={busy || running} onClick={() => void action(source, false, true)}>{source.autoAnalyze ? 'Выключить авто-AI' : 'Включить платный авто-AI'}</Button>
        </div>
      </section>
    })}
  </div>
}


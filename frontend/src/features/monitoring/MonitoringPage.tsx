import { useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { EmptyState, ErrorState, LoadingState, PageHeading } from '@/components/WorkspaceUI'
import { useApiQuery } from '@/lib/useApiQuery'
import { formatDate } from '@/lib/labels'
import { SourceManager } from './SourceManager'
import { FindingDetail } from './FindingDetail'
import { findingLabels, safeMonitorError, type Finding, type Source, type MonitorStatus, type Page, type Run } from './types'
import './monitoring.css'

export function MonitoringPage() {
  const [params, setParams] = useSearchParams()
  const view = params.get('view') === 'sources' ? 'sources' : params.get('view') === 'runs' ? 'runs' : 'queue'
  const status = ['new', 'investigating', 'dismissed'].includes(params.get('status') || '') ? params.get('status')! : ''
  const cursor = params.get('cursor') || ''
  const selected = params.get('item')
  const state = useApiQuery<MonitorStatus>('/api/v1/monitoring/status')
  const sources = useApiQuery<{ items: Source[] }>('/api/v1/monitoring/sources')
  const items = useApiQuery<Page<Finding>>(view === 'queue' ? '/api/v1/monitoring/items?limit=20' + (status ? '&status=' + status : '') + (cursor ? '&cursor=' + cursor : '') : null)
  const runs = useApiQuery<Page<Run>>(view === 'runs' ? '/api/v1/monitoring/runs?limit=20' + (cursor ? '&cursor=' + cursor : '') : null)
  function set(values: Record<string, string | null>) {
    const next = new URLSearchParams(params)
    Object.entries(values).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key))
    setParams(next)
  }
  function refresh() { state.refresh(); sources.refresh(); items.refresh(); runs.refresh() }
  useEffect(() => {
    if (view !== 'queue') return
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') { items.refresh(); state.refresh() }
    }, 30000)
    return () => window.clearInterval(timer)
  }, [view, items.refresh, state.refresh])
  const page = view === 'runs' ? runs.data : items.data
  return <div className="monitoring">
    <PageHeading eyebrow="Публичные источники → находки → эксперт" title="Мониторинг рекламы" description="Сбор материалов и предварительных признаков риска. Юридические факты подтверждает человек." action={<Button variant="outline" onClick={refresh}>Обновить мониторинг</Button>} />
    <section className="monitor-instagram" aria-label="Доступность Instagram-таргета"><div><span className="monitor-tag">Instagram · приоритетный источник</span><h2>Автосбор таргетированной рекламы KZ пока не подключён</h2><p>Стандартный Meta Ads Archive API ограничивает доступ к обычной рекламе, не показывавшейся в ЕС. Поиск публичных постов не заменяет сбор таргета.</p></div>
      <a className="detail-link" href="https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=KZ&search_type=keyword_unordered" target="_blank" rel="noopener noreferrer">Открыть Meta Ad Library · Казахстан ↗</a>
    </section>
    <section className="monitor-summary" aria-label="Состояние мониторинга">
      <div><strong>Регулярный запуск</strong><p>{state.data?.workerLastTickAt ? 'Worker проверял источники: ' + formatDate(state.data.workerLastTickAt) : 'Ещё не подтверждён. Ручной сбор доступен в источниках.'}</p></div>
      <div><strong>Запросы к источникам сегодня, UTC</strong><p>{state.data ? state.data.dailyFetchUsed + ' / ' + state.data.dailyFetchLimit : 'Загружаем…'}</p></div>
      <div><strong>Покрытие</strong><p>Выдача интернет-поиска и последние текстовые посты выбранных Telegram-каналов. Изображения, Stories и закрытые профили не собираются.</p></div>
    </section>
    {state.error && <ErrorState message={state.error} retry={state.refresh} />}
    <nav className="monitor-tabs" aria-label="Разделы мониторинга">
      {([['queue', 'Очередь эксперта'], ['sources', 'Источники сбора'], ['runs', 'История запусков']] as const).map(([key, label]) => <Button variant={view === key ? 'default' : 'outline'} key={key} aria-pressed={view === key} onClick={() => set({ view: key, cursor: null })}>{label}</Button>)}
    </nav>
    {view === 'sources' ? <>{sources.loading && <LoadingState />}{sources.error && <ErrorState message={sources.error} retry={sources.refresh} />}<SourceManager sources={sources.data?.items || []} changed={refresh} /></>
      : view === 'runs' ? <section className="panel"><h2>Запуски сбора</h2>
        {runs.loading ? <LoadingState /> : runs.error ? <ErrorState message={runs.error} retry={runs.refresh} /> : !runs.data?.items.length ? <p>Запусков ещё не было.</p> : runs.data.items.map(run => <article className="monitor-run" key={run.id}>
          <strong>{run.status === 'succeeded' ? 'Сбор завершён' : run.status === 'failed' ? 'Сбор не выполнен' : 'Сбор выполняется'}</strong>
          <p>{sources.data?.items.find(s => s.id === run.sourceId)?.name || 'Источник'} · {formatDate(run.createdAt)}</p>
          <p>Прочитано {run.fetched} · Подходит под фильтр {run.relevant} · Новых {run.created} · Повторов {run.duplicates}</p>
          {run.limited && <p>Достигнут лимит страницы. Это не полный охват источника.</p>}
          {run.errorCode && <p className="inline-notice">{safeMonitorError(run.errorCode)}</p>}
          {run.autoAiStatus && <p>Авто-AI: {run.autoAiStatus === 'succeeded' ? 'анализ сохранён' : safeMonitorError(run.autoAiStatus)}</p>}
        </article>)}
      </section> : <>
        <div className="monitor-filter"><label htmlFor="monitor-filter">Статус находки</label><select id="monitor-filter" value={status} onChange={e => set({ status: e.target.value, cursor: null })}><option value="">Все находки</option><option value="new">Новые</option><option value="investigating">В работе эксперта</option><option value="dismissed">Отложенные</option></select><span>Регион и слова оплаты — предварительный фильтр, не подтверждённый факт.</span></div>
        <div className="monitor-layout"><section aria-label="Найденные публикации">
          {items.loading ? <LoadingState /> : items.error ? <ErrorState message={items.error} retry={items.refresh} /> : !items.data?.items.length ? <EmptyState title="В этой очереди пока нет находок"><p>Это не означает отсутствия рекламы. Проверьте источники и историю запусков.</p><Button variant="outline" onClick={() => set({ view: 'sources', cursor: null })}>Настроить источники</Button></EmptyState> : items.data.items.map(item => <article className={'panel monitor-finding' + (selected === item.id ? ' selected' : '')} key={item.id}>
            <div className="monitor-heading"><span className="monitor-tag">{findingLabels[item.status]}</span><span>{item.contentKind === 'search_snippet' ? 'Фрагмент поиска' : 'Telegram'}</span></div>
            <h2>{item.title || item.account}</h2><p className="monitor-preview">{item.text}</p>
            {item.paymentMatches.length > 0 && <p className="monitor-attention">Есть слова об оплате — проверить</p>}
            <p className="form-hint">Получено {formatDate(item.createdAt)} · {item.aiStatus === 'succeeded' ? 'AI-анализ готов' : item.aiStatus === 'failed' ? 'AI-анализ не выполнен' : item.aiStatus === 'running' ? 'AI выполняется' : 'Без AI-анализа'}</p>
            <Button variant={selected === item.id ? 'default' : 'outline'} onClick={() => set({ item: item.id })}>Рассмотреть находку</Button>
          </article>)}
        </section>
          {selected ? <FindingDetail key={selected} id={selected} liveRegistry={Boolean(state.data?.liveRegistryEnabled)} changed={refresh} /> : <section className="panel"><h2>Выберите находку</h2><p>Откройте оригинал, проверьте контекст и сохраните решение. Совпадения слов сами не меняют риск ЖК.</p></section>}
        </div>
      </>}
    {view !== 'sources' && (cursor || page?.nextCursor) && <div className="form-actions"><Button variant="outline" onClick={() => set({ cursor: null })}>В начало списка</Button>{page?.nextCursor && <Button variant="outline" onClick={() => set({ cursor: page.nextCursor })}>Далее по списку</Button>}</div>}
  </div>
}


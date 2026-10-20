import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { ErrorState, LoadingState } from '@/components/WorkspaceUI'
import { useApiQuery } from '@/lib/useApiQuery'
import { formatDate } from '@/lib/labels'
import { SourceManager } from '@/features/monitoring/SourceManager'
import { safeMonitorError, type MonitorStatus, type Source, type Run, type Page } from '@/features/monitoring/types'
import '@/features/monitoring/monitoring.css'

export function SourcesSchedule() {
  const [params, setParams] = useSearchParams()
  const [historyOpen, setHistoryOpen] = useState(params.get('runs') === '1')
  const status = useApiQuery<MonitorStatus>('/api/v1/monitoring/status')
  const sources = useApiQuery<{ items: Source[] }>('/api/v1/monitoring/sources')
  const cursor = params.get('runCursor') || ''
  const runs = useApiQuery<Page<Run>>(historyOpen ? '/api/v1/monitoring/runs?limit=20' + (cursor ? '&cursor=' + encodeURIComponent(cursor) : '') : null)
  function refresh() { status.refresh(); sources.refresh(); if (historyOpen) runs.refresh() }
  return <div className="monitoring ad-stack">
    <section className="panel"><h2>Источники и расписание</h2>
      <p>{status.data?.workerLastTickAt ? 'Последняя проверка источников: ' + formatDate(status.data.workerLastTickAt) : 'Регулярный запуск ещё не подтверждён. Проверьте состояние источников.'}</p>
      <Button variant="outline" onClick={refresh}>Обновить источники</Button>
      {status.error && <ErrorState message={status.error} retry={status.refresh} />}
      <details><summary>Покрытие и ограничения</summary>
        <p>Instagram через Meta Ad Library/SearchAPI, фрагменты интернет-поиска и публичные тексты Telegram. Полный охват не гарантируется. Внешние файлы и Stories автоматически не скачиваются.</p>
        <p>{status.data?.instagramTargetedAds === 'configured' ? 'Источник Instagram настроен.' : 'Источник Instagram пока не подключён.'}</p>
        <a className="detail-link" href="https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=KZ&search_type=keyword_unordered" target="_blank" rel="noopener noreferrer">Открыть Meta Ad Library · Казахстан ↗</a>
        {status.data?.searchApi && <p>Резерв поисков: {status.data.searchApi.creditReserve}. Использовано сегодня: {status.data.searchApi.dailyUsed} / {status.data.searchApi.dailyLimit}.
          Остаток перед последним поиском: {status.data.searchApi.creditsObservedBefore ?? 'неизвестен'}; проверен {formatDate(status.data.searchApi.checkedAt)}. Это не текущий баланс.
          Незавершённых попыток: {status.data.searchApi.unsettledAttempts}.</p>}
        {status.data && <p>Запросы к источникам сегодня, UTC: {status.data.dailyFetchUsed} / {status.data.dailyFetchLimit}.</p>}
      </details>
    </section>
    {sources.loading ? <LoadingState /> : sources.error ? <ErrorState message={sources.error} retry={sources.refresh} />
      : <SourceManager sources={sources.data?.items || []} provider={status.data} changed={refresh} />}
    <details className="panel" open={historyOpen} onToggle={event => setHistoryOpen(event.currentTarget.open)}>
      <summary>История запусков</summary>
      {historyOpen && <div className="ad-stack">
        {runs.loading ? <LoadingState /> : runs.error ? <ErrorState message={runs.error} retry={runs.refresh} /> : !runs.data?.items.length ? <p>Запусков ещё не было.</p>
          : runs.data.items.map(run => <article className="monitor-run" key={run.id}>
            <h3>{run.status === 'succeeded' ? 'Сбор завершён' : run.status === 'failed' ? 'Сбор не выполнен' : 'Сбор выполняется'}</h3>
            <p>{sources.data?.items.find(source => source.id === run.sourceId)?.name || 'Источник'} · {formatDate(run.createdAt)}</p>
            <p>Прочитано {run.fetched} · Подходит {run.relevant} · Новых {run.created} · Повторов {run.duplicates}</p>
            {Boolean(run.unreadable) && <p>Без доступного текста или поддерживаемого формата: {run.unreadable}.</p>}
            {run.limited && <p>Достигнут лимит страницы, это не полный охват.</p>}
            {run.errorCode && <p>{safeMonitorError(run.errorCode)}</p>}
            {run.autoAiStatus && <p>Автоанализ: {run.autoAiStatus === 'succeeded' ? 'результат сохранён' : safeMonitorError(run.autoAiStatus)}</p>}
            {run.providerCreditsBefore != null && <p>Остаток перед поиском: {run.providerCreditsBefore}.</p>}
          </article>)}
        <div className="form-actions">{cursor && <Button variant="outline" onClick={() => { const next = new URLSearchParams(params); next.delete('runCursor'); setParams(next) }}>В начало истории</Button>}
          {runs.data?.nextCursor && <Button variant="outline" onClick={() => { const next = new URLSearchParams(params); next.set('runCursor', runs.data!.nextCursor!); setParams(next) }}>Следующие запуски</Button>}</div>
      </div>}
    </details>
  </div>
}

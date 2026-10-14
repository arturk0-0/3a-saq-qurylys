import { useEffect, useState } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { getHealth } from '@/lib/api'
import { ConfigurationNotice, useAuth } from '@/features/auth/AuthProvider'
import { LoginPage } from '@/features/auth/LoginPage'

const modules = [
  { path: '/', title: 'Обзор' },
  { path: '/complexes', title: 'Реестр ЖК' },
  { path: '/advertisements', title: 'Объявления' },
  { path: '/signals', title: 'Сигналы' },
]

function Overview() {
  const [status, setStatus] = useState('Проверяем соединение с API…')
  const [attempt, setAttempt] = useState(0)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let active = true
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 8000)
    setLoading(true)
    setStatus('Проверяем соединение с API…')
    getHealth(controller.signal)
      .then(() => { if (active) setStatus('API доступен') })
      .catch((error: unknown) => {
        if (!active) return
        setStatus(error instanceof Error && error.name !== 'AbortError'
          ? error.message : 'API не ответил вовремя. Проверьте запуск backend.')
      })
      .finally(() => { window.clearTimeout(timeout); if (active) setLoading(false) })
    return () => { active = false; window.clearTimeout(timeout); controller.abort() }
  }, [attempt])
  return <>
    <h1 className="text-2xl font-semibold">Обзор</h1>
    <p className="mt-3 text-muted-foreground">Каркас приложения для аналитиков Восточно-Казахстанской области.</p>
    <section className="mt-6 rounded-lg border border-border bg-background p-6" aria-label="Соединение с API">
      <h2 className="font-semibold">Состояние подключения</h2>
      <p className="my-4" role="status">{status}</p>
      <Button variant="outline" disabled={loading} onClick={() => setAttempt(attempt + 1)}>Проверить снова</Button>
    </section>
  </>
}

function PendingModule({ title }: { title: string }) {
  return <><h1 className="text-2xl font-semibold">{title}</h1>
    <p className="mt-4 text-muted-foreground">Раздел ещё не реализован. Данные и рабочие операции появятся на следующих этапах.</p></>
}

export function App() {
  const { status, profile, error, logout } = useAuth()
  const [logoutError, setLogoutError] = useState<string | null>(null)
  if (status !== 'authenticated') return <div className="min-h-screen bg-muted px-4 py-16">
    {status === 'unavailable' ? <ConfigurationNotice />
      : status === 'loading' ? <p role="status" className="text-center">Проверяем доступ…</p>
      : status === 'denied' ? <section className="mx-auto max-w-lg rounded-xl bg-background p-8">
        <h1 className="text-2xl font-semibold">Доступ не подтверждён</h1>
        <p className="my-4" role="alert">{error}</p>
        <p className="mb-4 text-sm">Администратор должен назначить роль аналитика и настроить backend.
          После этого войдите снова.</p>
        <Button onClick={() => { logout().catch(() => setLogoutError('Не удалось выйти. Повторите.')) }}>Выйти</Button>
        {logoutError && <p role="alert">{logoutError}</p>}
      </section> : <LoginPage />}
  </div>
  return <div className="min-h-screen bg-muted text-foreground">
    <header className="border-b border-border bg-background px-6 py-4">
      <span className="font-bold tracking-wide">SAQ QURYLYS</span>
      <span className="ml-4 text-sm text-muted-foreground">ВКО · {profile?.displayName || profile?.email || 'Аналитик'}</span>
      <Button variant="outline" size="sm" className="ml-4" onClick={() => { logout().catch(() => setLogoutError('Не удалось выйти. Повторите.')) }}>Выйти</Button>
      {logoutError && <p role="alert">{logoutError}</p>}
    </header>
    <div className="mx-auto flex max-w-7xl flex-col md:flex-row">
      <nav aria-label="Основная навигация" className="flex shrink-0 flex-wrap gap-2 p-4 md:w-56 md:flex-col">
        {modules.map(({ path, title }) => <NavLink key={path} to={path} end={path === '/'}
          className={({ isActive }) => `rounded-md px-4 py-3 text-sm ${isActive ? 'bg-primary text-primary-foreground' : 'hover:bg-background'}`}>
          {title}
        </NavLink>)}
      </nav>
      <main className="min-w-0 flex-1 p-6 md:p-8">
        <p className="mb-6 rounded-md border border-border bg-background p-3 text-sm">
          DEMO-среда · Синтетические записи используются для демонстрации и проверки сценариев.
        </p>
        <Routes>
          <Route path="/" element={<Overview />} />
          {modules.slice(1).map(({ path, title }) => <Route key={path} path={path} element={<PendingModule title={title} />} />)}
          <Route path="*" element={<PendingModule title="Страница не найдена" />} />
        </Routes>
      </main>
    </div>
  </div>
}

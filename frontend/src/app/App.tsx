import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { NavLink, Route, Routes, Link, useLocation } from 'react-router-dom'
import { Building2, LayoutDashboard, LogOut, Megaphone, ShieldCheck, FileCheck2, MapPin } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ConfigurationNotice, useAuth } from '@/features/auth/AuthProvider'
import { LoginPage } from '@/features/auth/LoginPage'
import { EmptyState, LoadingState } from '@/components/WorkspaceUI'
import { RouteBoundary } from './RouteBoundary'

const ComplexList = lazy(() => import('@/features/complexes/ComplexList').then(module => ({ default: module.ComplexList })))
const ComplexDetail = lazy(() => import('@/features/complexes/ComplexDetail').then(module => ({ default: module.ComplexDetail })))
const AdvertisementsPage = lazy(() => import('@/features/advertisements/AdvertisementsPage').then(module => ({ default: module.AdvertisementsPage })))
const AdvertisementDetail = lazy(() => import('@/features/advertisements/AdvertisementsPage').then(module => ({ default: module.AdvertisementDetail })))
const SignalsPage = lazy(() => import('@/features/signals/SignalsPage').then(module => ({ default: module.SignalsPage })))
const CreateSignal = lazy(() => import('@/features/signals/SignalsPage').then(module => ({ default: module.CreateSignal })))
const SignalDetail = lazy(() => import('@/features/signals/SignalsPage').then(module => ({ default: module.SignalDetail })))

const modules = [
  { path: '/', title: 'Обзор', icon: LayoutDashboard },
  { path: '/complexes', title: 'Реестр ЖК', icon: Building2 },
  { path: '/advertisements', title: 'Объявления', icon: Megaphone },
  { path: '/signals', title: 'Сигналы', icon: FileCheck2 },
]

function focusMainContent() {
  const main = document.getElementById('main-content')
  main?.focus({ preventScroll: true })
  main?.scrollIntoView?.({ block: 'start' })
}

export function App() {
  const { status, profile, error, logout } = useAuth()
  const [logoutError, setLogoutError] = useState<string | null>(null)
  const { pathname } = useLocation()
  const previousPath = useRef(pathname)
  useEffect(() => {
    if (previousPath.current !== pathname && status === 'authenticated') {
      focusMainContent()
    }
    previousPath.current = pathname
  }, [pathname, status])
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
  return <div className="workspace-shell">
    <a href="#main-content" className="skip-link" onClick={event => { event.preventDefault(); focusMainContent() }}>К содержимому</a>
    <aside className="sidebar">
      <Link to="/" className="brand"><span className="brand-symbol"><ShieldCheck size={25} /></span><span>SAQ <b>QURYLYS</b><small>Система проверки рисков</small></span></Link>
      <div className="sidebar-label">РАБОЧЕЕ ПРОСТРАНСТВО</div>
      <nav aria-label="Основная навигация">
        {modules.map(({ path, title, icon: Icon }) => <NavLink key={path} to={path} end={path === '/'}
          className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <Icon size={19} />{title}
        </NavLink>)}
      </nav>
      <div className="sidebar-note"><ShieldCheck size={22} /><strong>Решение за человеком</strong><p>AI помогает находить гипотезы. Факты подтверждает аналитик.</p></div>
      <div className="sidebar-region"><MapPin size={15} /> Восточно-Казахстанская область</div>
    </aside>
    <div className="workspace-main">
      <header className="topbar"><div><span className="demo-badge">DEMO</span><span className="topbar-context">Внутренний аналитический контур</span></div>
        <div className="user-menu"><span className="avatar">{(profile?.displayName || profile?.email || 'А').slice(0, 1).toUpperCase()}</span><span><strong>{profile?.displayName || profile?.email || 'Аналитик'}</strong><small>{profile?.role === 'admin' ? 'Администратор' : 'Аналитик'}</small></span>
          <button type="button" className="icon-button" aria-label="Выйти" onClick={() => { logout().catch(() => setLogoutError('Не удалось выйти. Повторите.')) }}><LogOut size={18} /></button></div>
      </header>
      <main id="main-content" className="workspace-content" tabIndex={-1}>
        {logoutError && <p role="alert" className="inline-notice">{logoutError}</p>}
        <RouteBoundary key={pathname}><Suspense fallback={<LoadingState />}><Routes>
          <Route path="/" element={<ComplexList overview />} />
          <Route path="/complexes" element={<ComplexList />} />
          <Route path="/complexes/:id" element={<ComplexDetail />} />
          <Route path="/advertisements" element={<AdvertisementsPage />} />
          <Route path="/advertisements/:id" element={<AdvertisementDetail />} />
          <Route path="/signals" element={<SignalsPage />} />
          <Route path="/signals/new" element={<CreateSignal />} />
          <Route path="/signals/:id" element={<SignalDetail />} />
          <Route path="*" element={<EmptyState title="Страница не найдена"><Link to="/">Вернуться к обзору</Link></EmptyState>} />
        </Routes></Suspense></RouteBoundary>
      </main>
    </div>
  </div>
}

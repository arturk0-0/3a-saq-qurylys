import { useState } from 'react'
import { NavLink, Route, Routes, Link } from 'react-router-dom'
import { Building2, LayoutDashboard, LogOut, Megaphone, ShieldCheck, FileCheck2, MapPin } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ConfigurationNotice, useAuth } from '@/features/auth/AuthProvider'
import { LoginPage } from '@/features/auth/LoginPage'
import { ComplexList } from '@/features/complexes/ComplexList'
import { ComplexDetail } from '@/features/complexes/ComplexDetail'
import { AdvertisementsPage } from '@/features/advertisements/AdvertisementsPage'
import { EmptyState } from '@/components/WorkspaceUI'

const modules = [
  { path: '/', title: 'Обзор', icon: LayoutDashboard },
  { path: '/complexes', title: 'Реестр ЖК', icon: Building2 },
  { path: '/advertisements', title: 'Объявления', icon: Megaphone },
  { path: '/signals', title: 'Сигналы', icon: FileCheck2 },
]

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
  return <div className="workspace-shell">
    <a href="#main-content" className="skip-link">К содержимому</a>
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
      <main id="main-content" className="workspace-content">
        {logoutError && <p role="alert" className="inline-notice">{logoutError}</p>}
        <Routes>
          <Route path="/" element={<ComplexList overview />} />
          <Route path="/complexes" element={<ComplexList />} />
          <Route path="/complexes/:id" element={<ComplexDetail />} />
          <Route path="/advertisements" element={<AdvertisementsPage />} />
          <Route path="/signals" element={<EmptyState title="Сигналы — следующий этап"><p>Сначала проверьте источники и факторы риска в карточке ЖК.</p></EmptyState>} />
          <Route path="*" element={<EmptyState title="Страница не найдена"><Link to="/">Вернуться к обзору</Link></EmptyState>} />
        </Routes>
      </main>
    </div>
  </div>
}

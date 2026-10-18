import { render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { ActorName } from './ActorName'
import { AuthContext, type Profile } from '@/features/auth/AuthProvider'

function show(uid: string, profile: Profile | null = null) {
  return render(<AuthContext.Provider value={{ profile, status: 'authenticated', error: null,
    api: vi.fn(), signIn: vi.fn(), logout: vi.fn() }}><ActorName uid={uid} /></AuthContext.Provider>)
}
it('uses the current profile name without exposing its UID', () => {
  const result = show('private-self-id', { uid: 'private-self-id', role: 'analyst', email: null, displayName: 'Айдана' })
  expect(screen.getByText('Айдана')).toBeVisible()
  expect(result.container.textContent).not.toContain('private-self-id')
})
it('never invents a name or exposes another reviewer UID', () => {
  const result = show('another-private-user-id')
  expect(screen.getByText('Аналитик')).toBeVisible()
  expect(result.container.innerHTML).not.toContain('another-private-user-id')
})
it('labels service and synthetic actors separately from human experts', () => {
  const result = show('service-monitor-worker')
  expect(screen.getByText('Автоматический сбор')).toBeVisible()
  result.unmount()
  show('DEMO-fictional-reviewer')
  expect(screen.getByText('Учебный эксперт')).toBeVisible()
})
it('shows You when the current profile has no display name', () => {
  show('self-id', { uid: 'self-id', role: 'analyst', email: null, displayName: null })
  expect(screen.getByText('Вы')).toBeVisible()
})

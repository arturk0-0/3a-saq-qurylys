import { useAuth } from '@/features/auth/AuthProvider'

// UIDs remain in server audit records; never expose them as a person's name.
export function ActorName({ uid }: { uid: string | null | undefined }) {
  const { profile } = useAuth()
  if (!uid) return <>Аналитик</>
  if (uid === 'service-monitor-worker') return <>Автоматический сбор</>
  if (uid === 'DEMO-fictional-reviewer') return <>Учебный эксперт</>
  if (uid === profile?.uid) return <>{profile.displayName?.trim() || 'Вы'}</>
  return <>Аналитик</>
}

import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { browserSessionPersistence, onIdTokenChanged, setPersistence, signInWithEmailAndPassword, signOut } from 'firebase/auth'
import { firebaseAuth, missingFirebaseConfig } from '@/lib/firebase'
import { createApiClient, type ApiClient } from '@/lib/http'

export interface Profile {
  uid: string
  role: 'analyst' | 'admin'
  email: string | null
  displayName: string | null
}

interface AuthState {
  status: 'loading' | 'signed_out' | 'authenticated' | 'unavailable' | 'denied'
  profile: Profile | null
  error: string | null
  api: ApiClient
  signIn: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('AuthProvider is required')
  return value
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthState['status']>(firebaseAuth ? 'loading' : 'unavailable')
  const [profile, setProfile] = useState<Profile | null>(null)
  const [error, setError] = useState<string | null>(null)
  const revision = useRef(0)
  const api = useMemo(() => createApiClient(async () => {
    if (!firebaseAuth?.currentUser) throw new Error('Требуется вход')
    return firebaseAuth.currentUser.getIdToken()
  }), [])

  useEffect(() => {
    if (!firebaseAuth) return
    const unsubscribe = onIdTokenChanged(firebaseAuth, async (user) => {
      const requestRevision = ++revision.current
      setProfile(null)
      setError(null)
      if (!user) { setStatus('signed_out'); return }
      setStatus('loading')
      try {
        const identity = await api<Profile>('/api/v1/me')
        if (requestRevision !== revision.current) return
        if (!['analyst', 'admin'].includes(identity.role)) throw new Error('Роль аналитика не назначена')
        setProfile(identity)
        setStatus('authenticated')
      } catch (error) {
        if (requestRevision !== revision.current) return
        setError(error instanceof Error ? error.message : 'Не удалось проверить доступ')
        setStatus('denied')
      }
    })
    return () => { revision.current += 1; unsubscribe() }
  }, [api])

  async function signIn(email: string, password: string) {
    if (!firebaseAuth) throw new Error('Firebase ещё не настроен')
    try {
      await setPersistence(firebaseAuth, browserSessionPersistence)
      await signInWithEmailAndPassword(firebaseAuth, email, password)
    } catch {
      throw new Error('Не удалось войти. Проверьте почту, пароль и подключение.')
    }
  }

  async function logout() {
    if (firebaseAuth) await signOut(firebaseAuth)
  }

  return <AuthContext.Provider value={{ status, profile, error, api, signIn, logout }}>
    {children}
  </AuthContext.Provider>
}

export function ConfigurationNotice() {
  return <section className="mx-auto max-w-xl rounded-xl border border-border bg-background p-8">
    <h1 className="text-2xl font-semibold">Подключите рабочую среду</h1>
    <p className="mt-4 text-muted-foreground">Для входа требуется настройка Firebase проекта SAQ QURYLYS.</p>
    <p className="mt-4 text-sm">Администратор должен заполнить browser-конфигурацию в .env
      и перезапустить frontend. Не заполнены: {missingFirebaseConfig.join(', ')}.</p>
    <p className="mt-4 text-sm text-muted-foreground">Инструкция: README → «Firebase и доступ аналитика».
      Серверные ключи нельзя размещать в browser-конфигурации.</p>
  </section>
}

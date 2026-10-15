import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { browserSessionPersistence, onIdTokenChanged, setPersistence, signInWithEmailAndPassword, signOut } from 'firebase/auth'
import { firebaseAuth, missingFirebaseConfig } from '@/lib/firebase'
import { ApiError, createApiClient, type ApiClient } from '@/lib/http'

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
  const api = useMemo<ApiClient>(() => {
    const client = createApiClient(async () => {
      if (!firebaseAuth?.currentUser) throw new ApiError(401, 'AUTH_REQUIRED', 'Сессия истекла. Войдите снова.')
      try {
        return await firebaseAuth.currentUser.getIdToken()
      } catch (error) {
        const code = error && typeof error === 'object' && 'code' in error ? error.code : null
        if (['auth/user-token-expired', 'auth/invalid-user-token', 'auth/user-disabled', 'auth/user-not-found'].includes(String(code))) {
          throw new ApiError(401, 'INVALID_TOKEN', 'Сессия истекла. Войдите снова.')
        }
        throw new ApiError(0, 'AUTH_UNAVAILABLE', 'Не удалось обновить доступ. Проверьте подключение и повторите.')
      }
    })
    return async <T,>(path: string, init?: RequestInit): Promise<T> => {
      const requestRevision = revision.current
      try {
        return await client<T>(path, init)
      } catch (error) {
        // A late response from an earlier session must not close a newer sign-in.
        if (error instanceof ApiError && error.status === 401 && requestRevision === revision.current) {
          revision.current += 1
          setProfile(null)
          setError('Сессия истекла. Войдите снова.')
          setStatus('denied')
        }
        throw error
      }
    }
  }, [])

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

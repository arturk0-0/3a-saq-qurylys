import { firebaseAuth, sessionKey, user } from './firebase'

const listeners = new Set<(value: typeof user | null) => unknown>()
export const browserSessionPersistence = {}
export async function setPersistence() {}
export function onIdTokenChanged(_auth: unknown, listener: (value: typeof user | null) => unknown) {
  listeners.add(listener)
  queueMicrotask(() => { if (listeners.has(listener)) listener(firebaseAuth.currentUser) })
  return () => { listeners.delete(listener) }
}
export async function signInWithEmailAndPassword(_auth: unknown, email: string, password: string) {
  const response = await fetch('/api/local-demo/session', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }),
  })
  if (!response.ok) throw new Error('Use the local demonstration account')
  const data = await response.json() as { token: string }
  sessionStorage.setItem(sessionKey, data.token)
  firebaseAuth.currentUser = user
  await Promise.all([...listeners].map(listener => listener(user)))
}
export async function signOut() {
  const token = sessionStorage.getItem(sessionKey)
  try {
    if (token) await fetch('/api/local-demo/session', { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } })
  } finally {
    sessionStorage.removeItem(sessionKey)
    firebaseAuth.currentUser = null
    await Promise.all([...listeners].map(listener => listener(null)))
  }
}

// No Firebase service, password, or real token is used by this adapter.
import { firebaseAuth, user } from './firebase'
const listeners = new Set<(value: typeof user | null) => unknown>()
export const browserSessionPersistence = {}
export async function setPersistence() {}
export function onIdTokenChanged(_auth: unknown, listener: (value: typeof user | null) => unknown) {
  listeners.add(listener)
  queueMicrotask(() => { if (listeners.has(listener)) listener(firebaseAuth.currentUser) })
  return () => { listeners.delete(listener) }
}
export async function signInWithEmailAndPassword(_auth: unknown, email: string, password: string) {
  if (email !== 'qa@example.test' || password !== 'local-test-only') throw new Error('Test sign-in rejected')
  sessionStorage.setItem('saq-qa-signed-in', 'yes')
  sessionStorage.removeItem('saq-qa-token')
  firebaseAuth.currentUser = user
  await Promise.all([...listeners].map(listener => listener(user)))
}
export async function signOut() {
  sessionStorage.removeItem('saq-qa-signed-in')
  firebaseAuth.currentUser = null
  await Promise.all([...listeners].map(listener => listener(null)))
}

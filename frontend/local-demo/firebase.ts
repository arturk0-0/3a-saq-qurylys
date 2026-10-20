// Resolved only by local-demo/vite.config.ts. Never used by Hosting builds.
const key = 'saq-local-demo-session'
export const missingFirebaseConfig: string[] = []
export const user = {
  getIdToken: async () => sessionStorage.getItem(key) || '',
}
export const firebaseAuth = { currentUser: sessionStorage.getItem(key) ? user : null as typeof user | null }
export const sessionKey = key

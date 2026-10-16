// Explicit local test adapter. Only release/vite.config.ts resolves this module.
export const missingFirebaseConfig: string[] = []
export const user = {
  getIdToken: async () => sessionStorage.getItem('saq-qa-token') || 'qa-local-analyst',
}
export const firebaseAuth = { currentUser: sessionStorage.getItem('saq-qa-signed-in') ? user : null as typeof user | null }

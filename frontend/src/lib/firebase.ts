import { initializeApp } from 'firebase/app'
import { getAuth } from 'firebase/auth'

const config = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY as string | undefined,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN as string | undefined,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID as string | undefined,
  appId: import.meta.env.VITE_FIREBASE_APP_ID as string | undefined,
}

export const missingFirebaseConfig = Object.entries(config)
  .filter(([, value]) => !value?.trim()).map(([name]) => name)

// Browser configuration is public. Admin credentials and Gemini keys never enter this module.
export const firebaseAuth = missingFirebaseConfig.length === 0
  ? getAuth(initializeApp(config)) : null

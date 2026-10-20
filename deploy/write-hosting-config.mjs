// Read only the public browser configuration; no Admin/Gemini credentials are involved.
import { writeFile } from 'node:fs/promises'

const api = process.argv[2]
if (!api || !/^https:\/\/[a-z0-9.-]+\.run\.app$/.test(api)) throw new Error('Provide the Cloud Run HTTPS origin')
const response = await fetch('https://saq-qurylys.web.app/__/firebase/init.json')
if (!response.ok) throw new Error('Cannot read public Firebase browser configuration')
const config = await response.json()
if (config.projectId !== 'saq-qurylys') throw new Error('Unexpected Firebase project')
const fields = { VITE_FIREBASE_API_KEY: config.apiKey, VITE_FIREBASE_AUTH_DOMAIN: config.authDomain,
  VITE_FIREBASE_PROJECT_ID: config.projectId, VITE_FIREBASE_APP_ID: config.appId, VITE_API_BASE_URL: api }
for (const [key, value] of Object.entries(fields)) {
  if (typeof value !== 'string' || !value || /[\r\n]/.test(value)) throw new Error(`Missing/invalid ${key}`)
}
await writeFile(new URL('../.env.production.local', import.meta.url), Object.entries(fields).map(([k, v]) => `${k}=${v}`).join('\n') + '\n', { mode: 0o600 })
console.log('Public Hosting build configuration saved; no secret values printed.')

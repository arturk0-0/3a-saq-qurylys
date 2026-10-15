import { loadEnv } from 'vite'

const env = loadEnv('production', '..', 'VITE_')
const required = ['VITE_FIREBASE_API_KEY', 'VITE_FIREBASE_AUTH_DOMAIN',
  'VITE_FIREBASE_PROJECT_ID', 'VITE_FIREBASE_APP_ID', 'VITE_API_BASE_URL']
const missing = required.filter((name) => !env[name]?.trim())
if (missing.length) {
  console.error(`Заполните .env.production.local в корне: ${missing.join(', ')}`)
  process.exit(1)
}
try {
  const base = new URL(env.VITE_API_BASE_URL)
  if (base.protocol !== 'https:' || base.username || base.password ||
    base.pathname !== '/' || base.search || base.hash) throw new Error('Invalid origin')
} catch {
  console.error('VITE_API_BASE_URL: нужен реальный HTTPS origin API без пути и credentials.')
  process.exit(1)
}
if (env.VITE_FIREBASE_PROJECT_ID !== 'saq-qurylys') {
  console.error('Firebase project в browser config не совпадает с saq-qurylys.')
  process.exit(1)
}
console.log('Обязательные настройки Hosting заданы; доступ к облачным сервисам не проверен.')

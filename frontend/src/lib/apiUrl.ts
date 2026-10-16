// Local Vite uses its same-origin proxy. Hosting calls Cloud Run directly so long
// analyses are not limited by Firebase Hosting's dynamic-request timeout.
export function apiUrl(path: string): string {
  if (!path.startsWith('/api/v1/')) throw new Error('Invalid API path')
  const configured = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim()
  if (!configured) return path
  let base: URL
  try { base = new URL(configured) } catch { throw new Error('Некорректный адрес API в настройках сайта.') }
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(base.hostname)
  if ((base.protocol !== 'https:' && !(base.protocol === 'http:' && local)) ||
    base.username || base.password || base.pathname !== '/' || base.search || base.hash) {
    throw new Error('Адрес API должен быть HTTPS origin без пути и учётных данных.')
  }
  return `${base.origin}${path}`
}

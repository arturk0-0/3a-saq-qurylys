export function materialQuery(params: URLSearchParams): string {
  const query = new URLSearchParams({ review: ['all', 'needs_review', 'reviewed', 'dismissed'].includes(params.get('review') || '') ? params.get('review')! : 'all',
    origin: ['automatic', 'manual'].includes(params.get('origin') || '') ? params.get('origin')! : 'all',
    sort: params.get('sort') === 'recent' ? 'recent' : 'priority', limit: '20' })
  for (const key of ['q', 'platform', 'complexId', 'cursor']) if (params.get(key)) query.set(key, params.get(key)!)
  return query.toString()
}
export function changedFilter(params: URLSearchParams, key: string, value: string): URLSearchParams {
  const next = new URLSearchParams(params)
  if (value) next.set(key, value); else next.delete(key)
  if (key !== 'cursor') next.delete('cursor')
  return next
}
export function legacyTarget(kind: 'monitoring' | 'advertisement', id: string | undefined, search: string): string {
  const params = new URLSearchParams(search)
  const selected = id || (kind === 'monitoring' && !['sources', 'runs'].includes(params.get('view') || '') ? params.get('item') : null)
  if (selected) return `/advertising/legacy/${kind}/${encodeURIComponent(selected)}${search}`
  if (params.has('cursor')) { params.set(kind === 'monitoring' && params.get('view') === 'runs' ? 'runCursor' : 'legacyCursor', params.get('cursor')!); params.delete('cursor') }
  if (kind === 'monitoring') {
    const view = params.get('view')
    if (view === 'sources' || view === 'runs') { params.set('view', 'sources'); if (view === 'runs') params.set('runs', '1') }
    else { params.delete('view'); if (params.get('status') && params.get('status') !== 'all') params.set('review', params.get('status') === 'dismissed' ? 'dismissed' : 'needs_review') }
  }
  if (params.has('complex')) params.set('complexId', params.get('complex')!)
  return '/advertising' + (params.size ? '?' + params : '')
}

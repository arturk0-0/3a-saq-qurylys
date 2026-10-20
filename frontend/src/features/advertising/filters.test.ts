import { expect, it } from 'vitest'
import { changedFilter, legacyTarget, materialQuery } from './filters'

it('requests all materials and server priority by default, and forwards opaque cursors unchanged', () => {
  expect(Object.fromEntries(new URLSearchParams(materialQuery(new URLSearchParams())))).toEqual({ review: 'all', origin: 'all', sort: 'priority', limit: '20' })
  const params = new URLSearchParams({ q: 'депозит & бронь', review: 'reviewed', origin: 'manual', platform: 'Instagram', complexId: 'c/1', cursor: 'opaque+/=', sort: 'recent', ignored: 'no' })
  expect(Object.fromEntries(new URLSearchParams(materialQuery(params)))).toEqual({ q: 'депозит & бронь', review: 'reviewed', origin: 'manual', platform: 'Instagram', complexId: 'c/1', cursor: 'opaque+/=', sort: 'recent', limit: '20' })
})

it('clears only the materials cursor for changed filters without losing other filters or mutating the URL', () => {
  const original = new URLSearchParams('q=old&review=reviewed&cursor=old-page')
  expect(changedFilter(original, 'q', 'new').toString()).toBe('q=new&review=reviewed')
  expect(original.get('cursor')).toBe('old-page')
  expect(changedFilter(original, 'cursor', 'next').get('q')).toBe('old')
})

it('keeps old selection/query and source-run pagination without treating old list cursors as material cursors', () => {
  expect(legacyTarget('monitoring', undefined, '?item=old%2Fid&status=new')).toBe('/advertising/legacy/monitoring/old%2Fid?item=old%2Fid&status=new')
  expect(legacyTarget('advertisement', 'ad/1', '?source=e1')).toBe('/advertising/legacy/advertisement/ad%2F1?source=e1')
  const runs = new URL(legacyTarget('monitoring', undefined, '?view=runs&item=stale&cursor=run2'), 'https://test.invalid')
  expect(runs.pathname).toBe('/advertising'); expect(runs.searchParams.get('view')).toBe('sources')
  expect(runs.searchParams.get('runCursor')).toBe('run2'); expect(runs.searchParams.get('runs')).toBe('1')
  const list = new URL(legacyTarget('advertisement', undefined, '?q=text&complex=c1&cursor=old'), 'https://test.invalid')
  expect(list.searchParams.get('complexId')).toBe('c1'); expect(list.searchParams.get('legacyCursor')).toBe('old')
  expect(list.searchParams.has('cursor')).toBe(false)
})

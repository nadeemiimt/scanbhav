/** Local bookmarks — persisted in localStorage for quick revisit. */

import { loadStore, saveStore } from './lib/storage'

export const BOOKMARKS_KEY = 'scanBhavBookmarks'

export function loadBookmarks() {
  const parsed = loadStore(BOOKMARKS_KEY, [])
  return Array.isArray(parsed) ? parsed : []
}

export function saveBookmarks(items) {
  saveStore(BOOKMARKS_KEY, items)
}

export function isBookmarked(symbol) {
  const sym = (symbol || '').toUpperCase()
  if (!sym) return false
  return loadBookmarks().some(b => (b.symbol || '').toUpperCase() === sym)
}

export function toggleBookmark(entry) {
  const sym = (entry?.symbol || '').toUpperCase()
  if (!sym) return { bookmarked: false, list: loadBookmarks() }

  const list = loadBookmarks()
  const idx = list.findIndex(b => (b.symbol || '').toUpperCase() === sym)
  if (idx >= 0) {
    list.splice(idx, 1)
    saveBookmarks(list)
    return { bookmarked: false, list }
  }

  list.unshift({
    symbol: sym,
    name: entry.name || sym,
    lastPrice: entry.lastPrice ?? null,
    changePct: entry.changePct ?? null,
    stance: entry.stance || '',
    asOf: entry.asOf || '',
    bookmarkedAt: new Date().toISOString(),
  })
  saveBookmarks(list)
  return { bookmarked: true, list }
}

export function removeBookmark(symbol) {
  const sym = (symbol || '').toUpperCase()
  const list = loadBookmarks().filter(b => (b.symbol || '').toUpperCase() !== sym)
  saveBookmarks(list)
  return list
}

/** Add many screener rows without removing existing bookmarks. */
export function addBookmarks(entries) {
  const list = loadBookmarks()
  const seen = new Set(list.map(b => (b.symbol || '').toUpperCase()))
  let added = 0
  for (const entry of entries || []) {
    const sym = (entry?.symbol || '').toUpperCase()
    if (!sym || seen.has(sym)) continue
    seen.add(sym)
    list.unshift({
      symbol: sym,
      name: entry.name || sym,
      lastPrice: entry.lastPrice ?? entry.price ?? null,
      changePct: entry.changePct ?? entry.horizon_return_pct ?? null,
      stance: entry.stance || '',
      asOf: entry.asOf || entry.as_of || '',
      bookmarkedAt: new Date().toISOString(),
    })
    added += 1
  }
  if (added > 0) saveBookmarks(list)
  return { list, added }
}

export function upsertBookmarkMeta(symbol, patch) {
  const sym = (symbol || '').toUpperCase()
  const list = loadBookmarks()
  const idx = list.findIndex(b => (b.symbol || '').toUpperCase() === sym)
  if (idx < 0) return list
  list[idx] = { ...list[idx], ...patch, symbol: sym }
  saveBookmarks(list)
  return list
}

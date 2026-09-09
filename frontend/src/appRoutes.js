/** Client-side routes — paths survive refresh (SPA fallback serves index.html). */

import { DEFAULT_SCREEN_UI } from './screenApi'

export const APP_TABS = ['single', 'multi', 'swing', 'autopilot', 'portfolio', 'accounts', 'coach', 'markets', 'method', 'about']

const TAB_TO_PATH = {
  single: '/',
  multi: '/multi',
  swing: '/swing',
  autopilot: '/autopilot',
  portfolio: '/portfolio',
  accounts: '/accounts',
  coach: '/coach',
  markets: '/markets',
  method: '/method',
  about: '/about',
}

const PATH_TO_TAB = {
  '/': 'single',
  '/single': 'single',
  '/multi': 'multi',
  '/swing': 'swing',
  '/autopilot': 'autopilot',
  '/portfolio': 'portfolio',
  '/accounts': 'accounts',
  '/coach': 'coach',
  '/markets': 'markets',
  '/method': 'method',
  '/about': 'about',
}

const SCREEN_URL_KEYS = {
  page: 'scr_page',
  pageSize: 'scr_ps',
  capView: 'scr_cap',
  viewMode: 'scr_view',
  symbolFilter: 'scr_sym',
  gradeFilter: 'scr_grade',
  stanceFilter: 'scr_stance',
  minScore: 'scr_min_score',
  maxScore: 'scr_max_score',
  minRsi: 'scr_min_rsi',
  maxRsi: 'scr_max_rsi',
  sortKey: 'scr_sort',
  sortDir: 'scr_sort_dir',
  sortKey2: 'scr_sort2',
  sortDir2: 'scr_sort2_dir',
}

export function normalizePathname(pathname = window.location.pathname) {
  const trimmed = (pathname || '/').replace(/\/+$/, '') || '/'
  return trimmed.toLowerCase()
}

export function tabFromPath(pathname = window.location.pathname) {
  return PATH_TO_TAB[normalizePathname(pathname)] || null
}

export function hasScreenQueryParams(search = window.location.search) {
  const params = new URLSearchParams(search)
  for (const key of params.keys()) {
    if (key.startsWith('scr_')) return true
  }
  return false
}

/** Resolve active tab from the current URL (path wins; scr_* implies multi). */
export function tabFromLocation(loc = window.location) {
  const fromPath = tabFromPath(loc.pathname)
  if (fromPath) return fromPath
  if (hasScreenQueryParams(loc.search)) return 'multi'
  return 'single'
}

export function pathForTab(tab) {
  return TAB_TO_PATH[tab] || '/'
}

function screenUiToParams(state) {
  const params = new URLSearchParams()
  for (const [field, param] of Object.entries(SCREEN_URL_KEYS)) {
    const value = state[field]
    const empty = value === '' || value == null
    if (field === 'page' && value === 1) continue
    if (field === 'pageSize' && value === 50) continue
    if (field === 'capView' && value === 'all') continue
    if (field === 'viewMode' && value === 'all') continue
    if (field === 'sortKey' && value === 'display_rank') continue
    if (field === 'sortDir' && value === 'asc') continue
    if (field === 'sortKey2' && value === 'score') continue
    if (field === 'sortDir2' && value === 'desc') continue
    if (empty && ['symbolFilter', 'gradeFilter', 'stanceFilter', 'minScore', 'maxScore', 'minRsi', 'maxRsi'].includes(field)) {
      continue
    }
    if (!empty) params.set(param, String(value))
  }
  return params
}

export function readScreenUiFromUrl(search = window.location.search) {
  const params = new URLSearchParams(search)
  const next = { ...DEFAULT_SCREEN_UI }
  let found = false
  for (const [field, param] of Object.entries(SCREEN_URL_KEYS)) {
    if (!params.has(param)) continue
    found = true
    const raw = params.get(param)
    if (field === 'page' || field === 'pageSize') {
      const n = Number(raw)
      if (Number.isFinite(n) && n > 0) {
        next[field] = field === 'pageSize' ? Math.min(100, Math.max(10, n)) : n
      }
    } else {
      next[field] = raw ?? next[field]
    }
  }
  return found ? next : null
}

export function buildAppUrl(tab, screenUi = null) {
  const path = pathForTab(tab)
  if (tab !== 'multi' || !screenUi) {
    return path
  }
  const params = screenUiToParams(screenUi)
  const qs = params.toString()
  return qs ? `${path}?${qs}` : path
}

/** Update the browser URL for tab + optional multi-screen state. */
export function writeAppUrl(tab, screenUi = null, { replace = true } = {}) {
  const url = buildAppUrl(tab, screenUi)
  const state = { tab, screenUi: tab === 'multi' ? screenUi : null }
  if (replace) {
    window.history.replaceState(state, '', url)
  } else {
    window.history.pushState(state, '', url)
  }
}

export function loadInitialAppRoute() {
  let tab = tabFromLocation()
  let screenUi = readScreenUiFromUrl() || null
  // Legacy bookmark: /?scr_page=2 → /multi?scr_page=2
  if (tab === 'single' && screenUi) {
    tab = 'multi'
  }
  return { tab, screenUi }
}

export { SCREEN_URL_KEYS }

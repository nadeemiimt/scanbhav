/** Screener UI state + /api/ta/screen/page client (Python contract v1). */

import { buildAppUrl, readScreenUiFromUrl, writeAppUrl } from './appRoutes'
import { apiFetch } from './lib/apiClient'
import { loadStore } from './lib/storage'

export { readScreenUiFromUrl } from './appRoutes'

export const SCREEN_UI_STORAGE_KEY = 'stock-adda-screen-ui-v1'

export const DEFAULT_SCREEN_UI = {
  page: 1,
  pageSize: 50,
  capView: 'all',
  viewMode: 'all',
  symbolFilter: '',
  gradeFilter: '',
  stanceFilter: '',
  minScore: '',
  maxScore: '',
  minRsi: '',
  maxRsi: '',
  qualityOk: false,
  debtOk: false,
  growthOk: false,
  minQuality: '',
  patternBias: '',
  sortKey: 'display_rank',
  sortDir: 'asc',
  sortKey2: 'score',
  sortDir2: 'desc',
  filtersOpen: false,
}

export function readScreenUiFromStorage() {
  const parsed = loadStore(SCREEN_UI_STORAGE_KEY, null, { storage: sessionStorage })
  if (!parsed) return null
  return { ...DEFAULT_SCREEN_UI, ...parsed }
}

export function loadScreenUiState() {
  return readScreenUiFromUrl() || readScreenUiFromStorage() || { ...DEFAULT_SCREEN_UI }
}

/** Persist screener filters/page to sessionStorage and /multi?scr_* URL. */
export function persistScreenUi(state, { replace = true } = {}) {
  try {
    sessionStorage.setItem(SCREEN_UI_STORAGE_KEY, JSON.stringify(state))
  } catch {
    /* ignore quota errors */
  }
  writeAppUrl('multi', state, { replace })
}

function optionalNum(value) {
  if (value === '' || value == null) return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

export function screenUiToQuery(ui) {
  return {
    page: ui.page,
    page_size: ui.pageSize,
    cap_view: ui.capView,
    symbol: ui.symbolFilter.trim(),
    grade: ui.gradeFilter,
    stance: ui.stanceFilter,
    min_score: optionalNum(ui.minScore),
    max_score: optionalNum(ui.maxScore),
    min_rsi: optionalNum(ui.minRsi),
    max_rsi: optionalNum(ui.maxRsi),
    quality_ok: ui.qualityOk ? true : null,
    debt_ok: ui.debtOk ? true : null,
    growth_ok: ui.growthOk ? true : null,
    min_quality: optionalNum(ui.minQuality),
    pattern_bias: ui.patternBias || '',
    sort_key: ui.sortKey,
    sort_dir: ui.sortDir,
    sort_key2: ui.sortKey2,
    sort_dir2: ui.sortDir2,
    view: ui.viewMode || 'all',
  }
}

export function buildScreenPageUrl(ui) {
  const q = screenUiToQuery(ui)
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(q)) {
    if (value === null || value === undefined || value === '') continue
    params.set(key, String(value))
  }
  return `/api/ta/screen/page?${params.toString()}`
}

export async function fetchScreenPage(ui, config = {}) {
  const url = buildScreenPageUrl(ui)
  const isDefault = ui.page === 1
    && ui.pageSize === 50
    && ui.capView === 'all'
    && ui.viewMode === 'all'
    && !ui.symbolFilter?.trim()
    && !ui.gradeFilter
    && !ui.stanceFilter
    && ui.minScore === ''
    && ui.maxScore === ''
    && ui.sortKey === 'display_rank'
    && ui.sortKey2 === 'score'
  if (isDefault) {
    try {
      return await apiFetch('/api/ta/screen/page-default', { method: 'GET' }, { timeoutMs: 8000, ...config })
    } catch {
      /* fall through to full page builder */
    }
  }
  return apiFetch(url, { method: 'GET' }, { timeoutMs: 45000, ...config })
}

/** Counts from /screen/last when /screen/page has not loaded yet. */
export function screenCountsFromLast(screen) {
  if (!screen?.sections) return null
  const large = screen.sections.large || {}
  const mid = screen.sections.mid || {}
  const small = screen.sections.small || {}
  const universe = screen.universe_size ?? 500
  const scored = screen.scored ?? 0
  const failed = screen.failed ?? 0
  return {
    universe,
    scanned: scored,
    pending: Math.max(0, universe - scored - failed),
    failed,
    all: universe,
    large: large.count ?? 100,
    mid: mid.count ?? 150,
    small: small.count ?? 250,
    large_scanned: large.scored ?? 0,
    mid_scanned: mid.scored ?? 0,
    small_scanned: small.scored ?? 0,
  }
}

/** Prefer the fresher/higher counts from page + last run summaries. */
export function mergeScreenCounts(screen, screenPage) {
  const page = screenPage?.counts
  const last = screenCountsFromLast(screen)
  const max = (a, b) => Math.max(a ?? 0, b ?? 0)
  if (!page && !last) return { scanned: null, universe: 500 }
  return {
    scanned: max(page?.scanned, last?.scanned) || 0,
    universe: page?.universe ?? last?.universe ?? 500,
    large: page?.large ?? last?.large ?? 0,
    mid: page?.mid ?? last?.mid ?? 0,
    small: page?.small ?? last?.small ?? 0,
    large_scanned: max(page?.large_scanned, last?.large_scanned),
    mid_scanned: max(page?.mid_scanned, last?.mid_scanned),
    small_scanned: max(page?.small_scanned, last?.small_scanned),
    pending: page?.pending ?? last?.pending ?? 0,
    failed: page?.failed ?? last?.failed ?? 0,
  }
}

/** Table contract: use page rows when ready; never show zero counts if /last has data. */
export function effectiveScreenPageContract(screenPage, screen, ui) {
  const merged = mergeScreenCounts(screen, screenPage)
  if (screenPage) {
    return {
      ...screenPage,
      counts: {
        ...(screenCountsFromLast(screen) || {}),
        ...screenPage.counts,
        ...merged,
        universe: merged.universe,
        scanned: merged.scanned,
        large: merged.large,
        mid: merged.mid,
        small: merged.small,
        large_scanned: merged.large_scanned,
        mid_scanned: merged.mid_scanned,
        small_scanned: merged.small_scanned,
      },
    }
  }
  if (!screen?.sections) return null
  return {
    counts: merged,
    rows: [],
    total_rows: 0,
    total_pages: 1,
    page: ui?.page ?? 1,
    page_size: ui?.pageSize ?? 50,
    run: {
      run_at: screen.run_at,
      scored: screen.scored,
      universe_size: screen.universe_size,
      failed: screen.failed,
      horizon: screen.horizon,
      data_provider: screen.data_provider,
      elapsed_seconds: screen.elapsed_seconds,
    },
    facets: { grades: [], stances: [] },
  }
}

export async function fetchScreenProviders() {
  try {
    return await apiFetch('/api/ta/screen/providers')
  } catch {
    return null
  }
}

export function applyPageContract(ui, pageContract) {
  if (!pageContract?.query) return ui
  const q = pageContract.query
  return {
    ...ui,
    page: q.page ?? ui.page,
    pageSize: q.page_size ?? ui.pageSize,
    capView: q.cap_view ?? ui.capView,
    symbolFilter: q.symbol ?? '',
    gradeFilter: q.grade ?? '',
    stanceFilter: q.stance ?? '',
    minScore: q.min_score ?? '',
    maxScore: q.max_score ?? '',
    minRsi: q.min_rsi ?? '',
    maxRsi: q.max_rsi ?? '',
    qualityOk: q.quality_ok === true,
    debtOk: q.debt_ok === true,
    growthOk: q.growth_ok === true,
    minQuality: q.min_quality ?? '',
    patternBias: q.pattern_bias ?? '',
    sortKey: q.sort_key ?? ui.sortKey,
    sortDir: q.sort_dir ?? ui.sortDir,
    sortKey2: q.sort_key2 ?? ui.sortKey2,
    sortDir2: q.sort_dir2 ?? ui.sortDir2,
    viewMode: q.view ?? ui.viewMode,
  }
}

export { buildAppUrl }

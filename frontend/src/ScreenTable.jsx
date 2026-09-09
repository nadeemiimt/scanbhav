import { useEffect, useMemo, useState } from 'react'
import { DEFAULT_SCREEN_UI, persistScreenUi } from './screenApi'

const number = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 })

const VIEW_MODES = [
  { id: 'all', label: 'All 500' },
  { id: 'scanned', label: 'Scanned' },
]

const CAP_VIEWS = [
  { id: 'all', label: 'All caps' },
  { id: 'large', label: 'Large' },
  { id: 'mid', label: 'Mid' },
  { id: 'small', label: 'Small' },
]

const BUCKET_LABEL = { large: 'L', mid: 'M', small: 'S' }

const CORE_COLUMNS = [
  { id: 'display_rank', label: '#', kind: 'num' },
  { id: 'scan_status', label: 'Scan', kind: 'status' },
  { id: 'scanned_at', label: 'Scanned at', kind: 'time' },
  { id: 'bucket', label: 'Cap', kind: 'text' },
  { id: 'symbol', label: 'Symbol', kind: 'text' },
  { id: 'price', label: 'Price', kind: 'num' },
  { id: 'entry_15d', label: 'Entry', kind: 'num' },
  { id: 'exit_15d', label: 'Exit', kind: 'num' },
  { id: 'stop_15d', label: 'Stop', kind: 'num' },
  { id: 'score', label: 'Score', kind: 'num' },
  { id: 'grade', label: 'Grade', kind: 'text' },
  { id: 'stance', label: 'Stance', kind: 'text' },
  { id: 'rsi_14', label: 'RSI', kind: 'num' },
  { id: 'atr_pct', label: 'ATR %', kind: 'num' },
]

const EXTRA_COLUMNS = [
  { id: 'atr_14', label: 'ATR', kind: 'num' },
  { id: 'composite_score', label: 'Composite', kind: 'num' },
  { id: 'horizon_return_pct', label: 'Horizon %', kind: 'num' },
  { id: 'macd_hist', label: 'MACD', kind: 'num' },
  { id: 'adx_14', label: 'ADX', kind: 'num' },
  { id: 'price_vs_sma_200_pct', label: 'vs SMA200', kind: 'num' },
  { id: 'quality_score', label: 'Quality', kind: 'num' },
  { id: 'pattern_bias', label: 'Pattern', kind: 'text' },
]

const ALL_COLUMNS = [...CORE_COLUMNS, ...EXTRA_COLUMNS]

function prettyStance(v) {
  return (v || '').replaceAll('_', ' ')
}

function formatScanTime(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'Asia/Kolkata',
    })
  } catch {
    return iso
  }
}

function scanStatusLabel(status) {
  if (status === 'scanned') return 'Done'
  if (status === 'failed') return 'Failed'
  if (status === 'pending') return 'Pending'
  return '—'
}

function rowRank(row, capView) {
  return capView === 'all' ? row.rank : (row.section_rank ?? row.rank)
}

function cellValue(row, col, capView) {
  if (col.id === 'display_rank') return rowRank(row, capView) ?? '—'
  if (col.id === 'bucket') return BUCKET_LABEL[row.bucket] || row.bucket || '—'
  if (col.id === 'scan_status') return scanStatusLabel(row.scan_status)
  if (col.id === 'scanned_at') return formatScanTime(row.scanned_at)
  const v = row[col.id]
  if (col.id === 'stance') return prettyStance(v)
  if (col.id === 'golden_cross') return v ? 'Yes' : 'No'
  if (col.id === 'supertrend_dir') {
    if (v === 1) return '▲'
    if (v === -1) return '▼'
    return '—'
  }
  if (col.kind === 'num' && v != null && v !== '') return number.format(v)
  return v ?? '—'
}

function capBadge(id, counts, viewMode) {
  const total = counts?.[id] ?? 0
  const scannedKey = id === 'all' ? 'scanned' : `${id}_scanned`
  const scanned = counts?.[scannedKey] ?? 0
  if (viewMode === 'scanned') return scanned
  if (id === 'all') return counts?.universe ?? total
  return total
}

function capSubBadge(id, counts) {
  if (id === 'all') {
    const scanned = counts?.scanned ?? 0
    return scanned > 0 ? `${scanned} scanned` : null
  }
  const scannedKey = `${id}_scanned`
  const scanned = counts?.[scannedKey]
  const total = counts?.[id] ?? 0
  if (scanned != null && total > 0) return `${scanned}/${total}`
  return null
}

function columnsWithPlanLabels(cols, planContext) {
  if (!planContext) return cols
  return cols.map(c => {
    if (c.id === 'entry_15d') return { ...c, label: planContext.entry_label || c.label }
    if (c.id === 'exit_15d') return { ...c, label: planContext.exit_label || c.label }
    if (c.id === 'stop_15d') return { ...c, label: planContext.stop_label || c.label }
    return c
  })
}

export default function ScreenTable({
  pageContract,
  ui,
  onUiChange,
  onRowClick,
  onCompareSymbols,
  onBookmarkSymbols,
  loading = false,
}) {
  const [selected, setSelected] = useState(() => new Set())
  const capView = ui?.capView ?? 'all'
  const viewMode = ui?.viewMode ?? 'all'
  const rows = pageContract?.rows ?? []
  const counts = pageContract?.counts ?? {}
  const run = pageContract?.run ?? {}
  const facets = pageContract?.facets ?? {}
  const grades = facets.grades ?? []
  const stances = facets.stances ?? []
  const totalRows = pageContract?.total_rows ?? 0
  const totalPages = pageContract?.total_pages ?? 1
  const page = pageContract?.page ?? ui?.page ?? 1
  const pageSize = pageContract?.page_size ?? ui?.pageSize ?? 50

  useEffect(() => {
    if (ui) persistScreenUi(ui)
  }, [ui])

  function patchUi(partial) {
    onUiChange?.(prev => ({ ...prev, ...partial }))
  }

  function toggleSort(colId) {
    if (ui.sortKey === colId) {
      patchUi({ sortDir: ui.sortDir === 'asc' ? 'desc' : 'asc', page: 1 })
    } else {
      patchUi({
        sortKey: colId,
        sortDir: colId === 'symbol' ? 'asc' : (colId === 'display_rank' ? 'asc' : 'desc'),
        page: 1,
      })
    }
  }

  function sortIndicator(colId) {
    if (ui.sortKey === colId) return ui.sortDir === 'asc' ? ' ↑' : ' ↓'
    if (ui.sortKey2 === colId) return ui.sortDir2 === 'asc' ? ' ↑₂' : ' ↓₂'
    return ''
  }

  const planContext = pageContract?.plan_context
  const visibleColumns = (() => {
    const base = ui.filtersOpen ? ALL_COLUMNS : CORE_COLUMNS
    const filtered = capView === 'all' ? base : base.filter(c => c.id !== 'bucket')
    return columnsWithPlanLabels(filtered, planContext)
  })()

  const rankStart = totalRows === 0 ? 0 : (page - 1) * pageSize + 1
  const rankEnd = Math.min(page * pageSize, totalRows)
  const universeTotal = counts.universe ?? counts.all ?? 500
  const scannedTotal = counts.scanned ?? 0

  const scannedRows = useMemo(
    () => rows.filter(r => r.scan_status === 'scanned' && r.symbol),
    [rows],
  )
  const selectedSymbols = useMemo(
    () => [...selected].sort((a, b) => a.localeCompare(b)),
    [selected],
  )
  const pageSelectedCount = scannedRows.filter(r => selected.has(r.symbol)).length
  const allPageSelected = scannedRows.length > 0 && pageSelectedCount === scannedRows.length
  const somePageSelected = pageSelectedCount > 0 && !allPageSelected

  function toggleSymbol(sym, checked) {
    const key = String(sym || '').toUpperCase()
    if (!key) return
    setSelected(prev => {
      const next = new Set(prev)
      if (checked) next.add(key)
      else next.delete(key)
      return next
    })
  }

  function togglePageSelection(checked) {
    setSelected(prev => {
      const next = new Set(prev)
      for (const row of scannedRows) {
        const sym = String(row.symbol).toUpperCase()
        if (checked) next.add(sym)
        else next.delete(sym)
      }
      return next
    })
  }

  function clearSelection() {
    setSelected(new Set())
  }

  function rowsForSelected() {
    return selectedSymbols.map(sym => rows.find(r => r.symbol === sym)).filter(Boolean)
  }

  async function copySelected() {
    if (!selectedSymbols.length) return
    const text = selectedSymbols.join(', ')
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="screen-table-wrap screen-table-compact">
      <div className="screen-run-meta">
        <span>{scannedTotal}/{universeTotal} scanned</span>
        {planContext?.target_day && (
          <span>
            {planContext.entry_label}
            {' · '}
            {planContext.ist_time} IST
          </span>
        )}
        {counts.pending > 0 && <span>{counts.pending} pending</span>}
        {counts.failed > 0 && <span className="down">{counts.failed} failed</span>}
        {run.run_at && <span>Last run {formatScanTime(run.run_at)}</span>}
      </div>

      <div className="screen-toolbar screen-toolbar-compact">
        <div className="screen-view-toggle" role="tablist" aria-label="Universe view">
          {VIEW_MODES.map(v => {
            const mainCount = v.id === 'all' ? universeTotal : scannedTotal
            const sub = v.id === 'all' && scannedTotal > 0 ? `${scannedTotal} scanned` : null
            return (
              <button
                key={v.id}
                type="button"
                role="tab"
                aria-selected={viewMode === v.id}
                className={viewMode === v.id ? 'primary screen-cap-btn' : 'ghost screen-cap-btn'}
                onClick={() => patchUi({ viewMode: v.id, page: 1, sortKey: v.id === 'scanned' ? 'score' : 'display_rank', sortDir: v.id === 'scanned' ? 'desc' : 'asc' })}
              >
                {v.label}
                <span className="screen-cap-count">{mainCount}</span>
                {sub && <span className="screen-cap-sub">{sub}</span>}
              </button>
            )
          })}
        </div>

        <div className="screen-cap-toggle" role="tablist" aria-label="Cap section">
          {CAP_VIEWS.map(v => {
            const sub = capSubBadge(v.id, counts)
            return (
              <button
                key={v.id}
                type="button"
                role="tab"
                aria-selected={capView === v.id}
                className={capView === v.id ? 'primary screen-cap-btn' : 'ghost screen-cap-btn'}
                onClick={() => patchUi({ capView: v.id, page: 1, sortKey: 'display_rank', sortDir: 'asc' })}
              >
                {v.label}
                <span className="screen-cap-count">{capBadge(v.id, counts, viewMode)}</span>
                {sub && viewMode === 'all' && <span className="screen-cap-sub">{sub}</span>}
              </button>
            )
          })}
        </div>

        <div className="screen-toolbar-filters">
          <label className="screen-inline-field">
            <span className="screen-inline-label">Symbol</span>
            <input
              value={ui.symbolFilter}
              onChange={e => patchUi({ symbolFilter: e.target.value, page: 1 })}
              placeholder="Search…"
            />
          </label>
          <label className="screen-inline-field">
            <span className="screen-inline-label">Grade</span>
            <select value={ui.gradeFilter} onChange={e => patchUi({ gradeFilter: e.target.value, page: 1 })}>
              <option value="">All</option>
              {grades.map(g => <option key={g} value={g}>{g}</option>)}
            </select>
          </label>
          <label className="screen-inline-field">
            <span className="screen-inline-label">Stance</span>
            <select value={ui.stanceFilter} onChange={e => patchUi({ stanceFilter: e.target.value, page: 1 })}>
              <option value="">All</option>
              {stances.map(s => <option key={s} value={s}>{prettyStance(s)}</option>)}
            </select>
          </label>
          <label className="screen-inline-field">
            <span className="screen-inline-label">Rows</span>
            <select value={ui.pageSize} onChange={e => patchUi({ pageSize: Number(e.target.value), page: 1 })}>
              {[25, 50, 100].map(n => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <button
            type="button"
            className="ghost screen-filter-toggle"
            onClick={() => patchUi({ filtersOpen: !ui.filtersOpen })}
            aria-expanded={ui.filtersOpen}
          >
            {ui.filtersOpen ? 'Less' : 'More'}
          </button>
        </div>
      </div>

      {totalRows === 0 && scannedTotal > 0 && !loading && (
        <p className="subtle screen-filter-empty">
          No rows match the current filters
          {(ui.qualityOk || ui.debtOk || ui.growthOk || ui.minScore || ui.maxScore || ui.minRsi || ui.maxRsi || ui.minQuality || ui.patternBias || ui.gradeFilter || ui.stanceFilter || ui.symbolFilter)
            ? ' — try clearing filters or switching cap view.'
            : ' — try switching cap view or refresh the page.'}
          {' '}
          <button type="button" className="linkish" onClick={() => patchUi({ ...DEFAULT_SCREEN_UI, page: 1 })}>
            Reset filters
          </button>
        </p>
      )}

      {ui.filtersOpen && (
        <div className="screen-filters-advanced screen-filters-compact">
          <label className="screen-inline-field">
            <span className="screen-inline-label">Min score</span>
            <input type="number" min="0" max="100" value={ui.minScore} onChange={e => patchUi({ minScore: e.target.value, page: 1 })} />
          </label>
          <label className="screen-inline-field">
            <span className="screen-inline-label">Max score</span>
            <input type="number" min="0" max="100" value={ui.maxScore} onChange={e => patchUi({ maxScore: e.target.value, page: 1 })} />
          </label>
          <label className="screen-inline-field">
            <span className="screen-inline-label">Min RSI</span>
            <input type="number" min="0" max="100" value={ui.minRsi} onChange={e => patchUi({ minRsi: e.target.value, page: 1 })} />
          </label>
          <label className="screen-inline-field">
            <span className="screen-inline-label">Max RSI</span>
            <input type="number" min="0" max="100" value={ui.maxRsi} onChange={e => patchUi({ maxRsi: e.target.value, page: 1 })} />
          </label>
          <label className="screen-inline-field">
            <span className="screen-inline-label">Min quality</span>
            <input type="number" min="0" max="100" value={ui.minQuality} onChange={e => patchUi({ minQuality: e.target.value, page: 1 })} />
          </label>
          <label className="screen-inline-field">
            <span className="screen-inline-label">Pattern</span>
            <select value={ui.patternBias} onChange={e => patchUi({ patternBias: e.target.value, page: 1 })}>
              <option value="">Any</option>
              <option value="bullish">Bullish</option>
              <option value="bearish">Bearish</option>
              <option value="neutral">Neutral</option>
            </select>
          </label>
          <label className="screen-inline-field screen-check-field">
            <input type="checkbox" checked={ui.qualityOk} onChange={e => patchUi({ qualityOk: e.target.checked, page: 1 })} />
            <span className="screen-inline-label">Quality OK</span>
          </label>
          <label className="screen-inline-field screen-check-field">
            <input type="checkbox" checked={ui.debtOk} onChange={e => patchUi({ debtOk: e.target.checked, page: 1 })} />
            <span className="screen-inline-label">Debt OK</span>
          </label>
          <label className="screen-inline-field screen-check-field">
            <input type="checkbox" checked={ui.growthOk} onChange={e => patchUi({ growthOk: e.target.checked, page: 1 })} />
            <span className="screen-inline-label">Growth OK</span>
          </label>
        </div>
      )}

      <p className="subtle screen-filter-count">
        {totalRows === 0 ? '0 rows' : `${rankStart}–${rankEnd} of ${totalRows}`}
        · p{page}/{totalPages}
        {viewMode === 'all' && totalRows !== universeTotal ? ` · filtered` : ''}
        {loading ? ' · …' : ''}
        {selectedSymbols.length > 0 ? ` · ${selectedSymbols.length} selected` : ''}
      </p>

      {selectedSymbols.length > 0 && (
        <div className="screen-selection-bar" role="toolbar" aria-label="Selected symbols">
          <span className="screen-selection-count">
            <strong>{selectedSymbols.length}</strong> selected
          </span>
          <button type="button" className="ghost screen-selection-btn" onClick={clearSelection}>
            Clear
          </button>
          <button
            type="button"
            className="ghost screen-selection-btn"
            onClick={() => togglePageSelection(!allPageSelected)}
          >
            {allPageSelected ? 'Deselect page' : 'Select page'}
          </button>
          <button
            type="button"
            className="ghost screen-selection-btn"
            disabled={selectedSymbols.length !== 1}
            onClick={() => onRowClick?.(selectedSymbols[0])}
          >
            Analyze
          </button>
          <button
            type="button"
            className="ghost screen-selection-btn"
            disabled={selectedSymbols.length < 2}
            onClick={() => onCompareSymbols?.(selectedSymbols.slice(0, 2))}
          >
            Compare
          </button>
          <button
            type="button"
            className="ghost screen-selection-btn"
            onClick={() => onBookmarkSymbols?.(rowsForSelected())}
          >
            Bookmark
          </button>
          <button type="button" className="ghost screen-selection-btn" onClick={copySelected}>
            Copy list
          </button>
        </div>
      )}

      <div className="table-wrap screen-table-scroll">
        <table className="screen-table">
          <thead>
            <tr>
              <th className="screen-select-col" aria-label="Select rows">
                <input
                  type="checkbox"
                  checked={allPageSelected}
                  ref={el => { if (el) el.indeterminate = somePageSelected }}
                  disabled={scannedRows.length === 0}
                  onChange={e => togglePageSelection(e.target.checked)}
                  aria-label="Select all on this page"
                />
              </th>
              {visibleColumns.map(col => (
                <th key={col.id}>
                  <button type="button" className="screen-sort-btn" onClick={() => toggleSort(col.id)}>
                    {col.label}{sortIndicator(col.id)}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(row => {
              const scanned = row.scan_status === 'scanned'
              const statusClass = row.scan_status ? `scan-${row.scan_status}` : ''
              const symKey = String(row.symbol || '').toUpperCase()
              const isSelected = selected.has(symKey)
              return (
                <tr
                  key={row.symbol}
                  className={[
                    scanned ? 'clickable' : '',
                    statusClass,
                    isSelected ? 'screen-row-selected' : '',
                  ].filter(Boolean).join(' ')}
                  onClick={scanned ? () => onRowClick?.(row.symbol) : undefined}
                >
                  <td className="screen-select-col" onClick={e => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={isSelected}
                      disabled={!scanned}
                      aria-label={`Select ${row.symbol}`}
                      onChange={e => toggleSymbol(row.symbol, e.target.checked)}
                    />
                  </td>
                  {visibleColumns.map(col => (
                    <td key={col.id} className={col.id === 'symbol' ? 'sym' : undefined}>
                      {cellValue(row, col, capView)}
                    </td>
                  ))}
                </tr>
              )
            })}
            {loading && rows.length === 0 && (
              <tr>
                <td colSpan={visibleColumns.length + 1} className="subtle">Loading rows…</td>
              </tr>
            )}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={visibleColumns.length + 1} className="subtle">No rows match these filters.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <nav className="screen-pagination" aria-label="Screener pages">
        <div className="screen-pagination-bar">
          <button type="button" className="screen-page-btn" disabled={page <= 1 || loading} onClick={() => patchUi({ page: 1 })}>First</button>
          <button type="button" className="screen-page-btn" disabled={page <= 1 || loading} onClick={() => patchUi({ page: page - 1 })}>Prev</button>
          <span className="screen-page-indicator">{page}/{totalPages}</span>
          <button type="button" className="screen-page-btn" disabled={page >= totalPages || loading} onClick={() => patchUi({ page: page + 1 })}>Next</button>
          <button type="button" className="screen-page-btn" disabled={page >= totalPages || loading} onClick={() => patchUi({ page: totalPages })}>Last</button>
        </div>
      </nav>
    </div>
  )
}

export { DEFAULT_SCREEN_UI }

import { useEffect, useMemo, useState } from 'react'
import { APP_NAME } from '../brand'
import { apiGetOptional } from '../lib/apiClient'

const DESK_TAB = {
  analyze: 'single',
  screener: 'multi',
  swing: 'swing',
  autopilot: 'autopilot',
  portfolio: 'portfolio',
}

export function IndicatorsReferencePage({ onNavigate }) {
  const [ref, setRef] = useState(null)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [openDesk, setOpenDesk] = useState('analyze')

  useEffect(() => {
    apiGetOptional('/api/ta/reference')
      .then(data => { if (data) setRef(data) })
      .catch(e => setError(e.message || 'Could not load reference'))
  }, [])

  const filtered = useMemo(() => {
    if (!ref?.all_indicators) return []
    const q = query.trim().toLowerCase()
    if (!q) return ref.all_indicators
    return ref.all_indicators.filter(row =>
      [row.id, row.title, row.what, row.why].some(v => String(v || '').toLowerCase().includes(q))
    )
  }, [ref, query])

  const categories = ref?.categories || []
  const byCategory = ref?.indicators_by_category || {}

  return (
    <div className="reference-page">
      <section className="panel reference-hero">
        <p className="eyebrow">REFERENCE</p>
        <h2>Indicators &amp; desk sections</h2>
        <p className="subtle reference-lede">
          Every technical input {APP_NAME} uses — and what each desk section on the platform does.
          Hover metrics on the Analyze page for the same copy inline.
        </p>
        {ref?.indicator_count != null && (
          <p className="subtle">
            <b>{ref.indicator_count}</b> documented indicators · {categories.length} categories · {ref.desk_sections?.length || 0} desk sections
          </p>
        )}
        {error && <p className="down">{error}</p>}
      </section>

      <section className="panel reference-section">
        <div className="panel-head">
          <div>
            <p className="eyebrow">DESKS</p>
            <h3>What each section does</h3>
          </div>
        </div>
        <div className="reference-desk-nav">
          {(ref?.desk_sections || []).map(sec => (
            <button
              key={sec.id}
              type="button"
              className={openDesk === sec.id ? 'primary' : 'ghost'}
              onClick={() => setOpenDesk(sec.id)}
            >
              {sec.label}
            </button>
          ))}
        </div>
        {(ref?.desk_sections || []).filter(s => s.id === openDesk).map(sec => (
          <article key={sec.id} className="reference-desk-detail">
            <h4>{sec.label}</h4>
            <p>{sec.summary}</p>
            <ul className="reason-list">
              {(sec.includes || []).map(line => (
                <li key={line}>{line}</li>
              ))}
            </ul>
            {DESK_TAB[sec.id] && onNavigate && (
              <button type="button" className="ghost" onClick={() => onNavigate(DESK_TAB[sec.id])}>
                Open {sec.label}
              </button>
            )}
          </article>
        ))}
        {!ref && !error && <p className="subtle">Loading desk guide…</p>}
      </section>

      <section className="panel reference-section">
        <div className="panel-head">
          <div>
            <p className="eyebrow">INDICATORS</p>
            <h3>Full catalog</h3>
          </div>
        </div>
        <label className="reference-search">
          Search indicators
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="e.g. RSI, ATR, pivot, volume…"
          />
        </label>

        {!query && categories.map(cat => {
          const rows = byCategory[cat.id] || []
          if (!rows.length) return null
          return (
            <details key={cat.id} className="reference-category" open>
              <summary>
                <span className="reference-cat-label">{cat.label}</span>
                <span className="subtle">{cat.summary}</span>
                <span className="reference-cat-count">{rows.length}</span>
              </summary>
              <div className="reference-grid">
                {rows.map(row => (
                  <article key={row.id} className="reference-card" id={`ind-${row.id}`}>
                    <h4>{row.title}</h4>
                    <p className="reference-id">{row.id}</p>
                    <p><strong>What:</strong> {row.what}</p>
                    <p className="subtle"><strong>Why useful:</strong> {row.why}</p>
                  </article>
                ))}
              </div>
            </details>
          )
        })}

        {query && (
          <div className="reference-grid">
            {filtered.length === 0 && <p className="subtle">No indicators match “{query}”.</p>}
            {filtered.map(row => (
              <article key={row.id} className="reference-card">
                <h4>{row.title}</h4>
                <p className="reference-id">{row.id}</p>
                <p><strong>What:</strong> {row.what}</p>
                <p className="subtle"><strong>Why useful:</strong> {row.why}</p>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="panel reference-section">
        <p className="eyebrow">NOTES</p>
        <ul className="reason-list compact">
          <li>Scores are educational heuristics — not investment advice or guaranteed predictions.</li>
          <li>Daily OHLCV from Yahoo/NSE; live LTP when broker stream is connected.</li>
          <li>Gen AI memos synthesize the same inputs — always verify against raw technical board data.</li>
        </ul>
      </section>
    </div>
  )
}

export default IndicatorsReferencePage

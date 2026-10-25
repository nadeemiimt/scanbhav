import { useEffect, useState } from 'react'
import { apiGetOptional } from '../lib/apiClient'

export function HorizonPicksPanel({ onAnalyze }) {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [active, setActive] = useState('7d')
  const [note, setNote] = useState('')

  async function load(refresh = false) {
    setBusy(true)
    setNote('')
    try {
      const path = `/api/ta/horizon-picks?top_n=8${refresh ? '&refresh=1' : ''}`
      const next = await apiGetOptional(path, {}, { timeoutMs: refresh ? 120000 : 45000 })
      if (!next) {
        setNote('Could not load horizon picks. Is the API running?')
        return
      }
      setData(next)
      if (next.boards?.length && !next.boards.find(b => b.id === active)) {
        setActive(next.boards[0].id)
      }
    } catch (err) {
      setNote(err.message || 'Failed to load picks')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => { load(false) }, [])

  const board = (data?.boards || []).find(b => b.id === active) || (data?.boards || [])[0]

  return (
    <section className="panel horizon-picks-panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">AUTO PICKS · BUY &amp; PLAN SELL</p>
          <h3>Top stocks by horizon</h3>
        </div>
        <button type="button" className="ghost" disabled={busy} onClick={() => load(true)}>
          {busy ? 'Updating…' : 'Refresh ranks'}
        </button>
      </div>
      <p className="subtle">
        Automatically ranks names for the next <b>7 days</b>, <b>15 days</b>, <b>30 days</b>, <b>6 months</b>, and <b>1 year</b>
        so you can plan buys and staged sells. Uses your last Nifty screen (refreshes from local prices if needed).
      </p>
      {!data?.ok && (
        <p className="subtle">{data?.message || 'Run Screener once, then Refresh ranks here.'}</p>
      )}
      {data?.ok && (
        <>
          <div className="horizon-pick-tabs" role="tablist">
            {(data.boards || []).map(b => (
              <button
                key={b.id}
                type="button"
                role="tab"
                className={b.id === board?.id ? 'tab active' : 'tab'}
                aria-selected={b.id === board?.id}
                onClick={() => setActive(b.id)}
              >
                {b.label}
              </button>
            ))}
          </div>
          {board && (
            <div className="horizon-pick-board">
              <p className="subtle">{board.hint}</p>
              <div className="horizon-pick-cols">
                <div>
                  <h4>Consider buying</h4>
                  <ul className="horizon-pick-list">
                    {(board.buy || []).map(row => (
                      <li key={`buy-${board.id}-${row.symbol}`}>
                        <button type="button" className="linkish" onClick={() => onAnalyze?.(row.symbol)}>
                          <b>{row.symbol}</b>
                        </button>
                        <span className={String(row.stance || '').includes('favorable') ? 'up' : ''}>
                          {row.score} · {row.grade || '—'}
                        </span>
                        <p className="subtle">{row.why}</p>
                      </li>
                    ))}
                    {!(board.buy || []).length && <li className="subtle">No buy candidates yet.</li>}
                  </ul>
                </div>
                <div>
                  <h4>Plan sell / avoid</h4>
                  <ul className="horizon-pick-list">
                    {(board.watch_sell || []).map(row => (
                      <li key={`sell-${board.id}-${row.symbol}`}>
                        <button type="button" className="linkish" onClick={() => onAnalyze?.(row.symbol)}>
                          <b>{row.symbol}</b>
                        </button>
                        <span className="down">{row.score} · {row.grade || '—'}</span>
                        <p className="subtle">{row.why}</p>
                      </li>
                    ))}
                    {!(board.watch_sell || []).length && <li className="subtle">No weak names flagged.</li>}
                  </ul>
                </div>
              </div>
            </div>
          )}
        </>
      )}
      {note && <p className="subtle">{note}</p>}
    </section>
  )
}

export function VerdictSummaryPanel({ summary }) {
  if (!summary) return null
  const tone = summary.verdict === 'good' ? 'up' : summary.verdict === 'bad' ? 'down' : ''
  return (
    <section className="panel verdict-summary-panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">WHY THIS STOCK</p>
          <h3 className={tone}>{summary.headline}</h3>
        </div>
        <span className={`subtle ${tone}`}>{summary.stance?.replace(/_/g, ' ')} · {summary.grade}</span>
      </div>
      <div className="verdict-summary-grid">
        <div>
          <h4 className="up">Why it looks good</h4>
          <ul className="subtle">
            {(summary.why_good || []).length
              ? summary.why_good.map(line => <li key={line}>{line}</li>)
              : <li>No strong positives on the scored horizons.</li>}
          </ul>
        </div>
        <div>
          <h4 className="down">Why it looks weak</h4>
          <ul className="subtle">
            {(summary.why_bad || []).length
              ? summary.why_bad.map(line => <li key={line}>{line}</li>)
              : <li>No major red flags listed.</li>}
          </ul>
        </div>
      </div>
      {summary.plan_7d_plain && <p className="subtle" style={{ marginTop: 8 }}>{summary.plan_7d_plain}</p>}
      {summary.buy_sell_plan && (
        <p className="subtle" style={{ marginTop: 6 }}>
          Plan levels — entry {summary.buy_sell_plan.entry ?? '—'} · exit {summary.buy_sell_plan.exit ?? '—'} · stop {summary.buy_sell_plan.stop ?? '—'}
        </p>
      )}
      {(summary.daywise_prediction || []).length > 0 && (
        <div className="daywise-prediction" style={{ marginTop: 12 }}>
          <h4>Day-wise scenario (next 7 days)</h4>
          <div className="table-wrap">
            <table className="forecast-table">
              <thead>
                <tr>
                  <th>Day</th>
                  <th>Date</th>
                  <th>Low</th>
                  <th>Mid</th>
                  <th>High</th>
                </tr>
              </thead>
              <tbody>
                {summary.daywise_prediction.map(row => (
                  <tr key={row.day || row.date}>
                    <td>{row.day}</td>
                    <td>{row.date}</td>
                    <td>{row.path_low}</td>
                    <td>{row.path_mid}</td>
                    <td>{row.path_high}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="subtle">Scenario path from the 7-day heuristic — not a guaranteed daily print.</p>
        </div>
      )}
    </section>
  )
}

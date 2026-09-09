import { useEffect, useState } from 'react'
import { apiGetOptional, apiPost } from '../../lib/apiClient'

function formatScanTime(iso) {
  if (!iso) return null
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

export function ConvictionUniversePanel({ onAnalyze, onRowClick }) {
  const [status, setStatus] = useState(null)
  const [rows, setRows] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [topN, setTopN] = useState(10)

  async function loadTop(n = topN) {
    setError('')
    const data = await apiGetOptional(`/api/ta/universe/conviction?top=${n}`)
    if (data?.rows) {
      setRows(data.rows)
      setStatus(prev => ({ ...prev, ready: true, ...data, total_scored: data.total_scored ?? prev?.scored }))
    }
  }

  useEffect(() => {
    apiGetOptional('/api/ta/universe/conviction/status')
      .then(s => { if (s) setStatus(s) })
      .catch(() => {})
    loadTop(topN).catch(() => {})
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    loadTop(topN).catch(() => {})
  }, [topN]) // eslint-disable-line react-hooks/exhaustive-deps

  async function runScan(force = false) {
    setBusy(true)
    setError('')
    try {
      const result = await apiPost(
        '/api/ta/universe/conviction/scan?force=' + (force ? 'true' : 'true')
        + '&limit=500&batch_size=50&batch_pause_seconds=4&retry_rounds=2&retry_pause_seconds=45&max_workers=4&batch_strategy=round_robin'
      )
      if (result?.error) throw new Error(result.error)
      if (result?.skipped) {
        await loadTop(topN)
      } else {
        setRows((result?.rows || []).slice(0, topN))
        setStatus({
          ready: true,
          last_run_at: result?.run_at,
          trade_date_ist: result?.trade_date_ist,
          scored: result?.scored,
        })
        await loadTop(topN)
      }
    } catch (e) {
      setError(e.message || 'Scan failed')
    } finally {
      setBusy(false)
    }
  }

  const scored = status?.scored ?? status?.total_scored
  const lastScan = formatScanTime(status?.last_run_at) || status?.trade_date_ist

  return (
    <section className="panel conviction-universe-panel conviction-compact">
      <div className="panel-head conviction-head-compact">
        <div>
          <p className="eyebrow">CONVICTION RAG</p>
          <h3>Top conviction · Nifty 500</h3>
        </div>
        <div className="conviction-universe-actions">
          <label className="conviction-top-select">
            Top
            <select value={topN} onChange={e => setTopN(Number(e.target.value))} disabled={busy}>
              {[5, 10, 20, 30, 50].map(n => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </label>
          <button type="button" className="ghost compact" disabled={busy} onClick={() => loadTop(topN)}>Refresh</button>
          <button type="button" className="primary compact" disabled={busy} onClick={() => runScan(true)}>
            {busy ? 'Scanning…' : 'Run scan'}
          </button>
        </div>
      </div>

      <p className="subtle conviction-meta-line">
        {scored != null ? `${scored}/500 in RAG` : 'No scan yet'}
        {lastScan ? ` · ${lastScan}` : ''}
        {scored != null && scored < 400 && (
          <span className="down"> · {scored}/500 scored — re-run for full coverage</span>
        )}
      </p>

      {error && <p className="down conviction-error">{error}</p>}

      {!rows.length && !busy && (
        <p className="subtle">Run screen first or click Run scan.</p>
      )}

      {rows.length > 0 && (
        <div className="conviction-universe-table-wrap">
          <table className="conviction-universe-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Symbol</th>
                <th>Conv</th>
                <th>Conf</th>
                <th>Comp</th>
                <th>Gr</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={row.symbol}>
                  <td>{i + 1}</td>
                  <td>
                    <button type="button" className="linkish" onClick={() => onRowClick?.(row.symbol)}>
                      {String(row.symbol || '').replace('.NSE', '')}
                    </button>
                  </td>
                  <td><strong>{row.conviction_score ?? '—'}</strong></td>
                  <td>{row.confidence ?? '—'}</td>
                  <td>{row.composite_score ?? '—'}</td>
                  <td>{row.grade ?? '—'}</td>
                  <td>
                    <button type="button" className="ghost compact" onClick={() => onAnalyze?.(row.symbol)}>
                      Analyze
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

export default ConvictionUniversePanel

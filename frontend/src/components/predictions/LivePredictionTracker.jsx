import { number, accuracyCopy, expectedMove, pretty } from '../../utils/analysisFormatters'

function fmtPinDate(item) {
  const d = item?.as_of || item?.created_at?.slice(0, 10)
  return d || '—'
}

function fmtRefresh(item) {
  const ts = item?.last_refreshed_at
  if (!ts) return 'Not refreshed yet'
  try {
    return new Date(ts).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })
  } catch {
    return ts.slice(0, 16).replace('T', ' ')
  }
}

export function LivePredictionTracker({ track, busy, onRefresh, onRate, onRemove, onTrackHere, canTrack, onAnalyze }) {
  const items = track?.items || []
  const openCount = items.filter(i => i.status === 'open').length
  const max = track?.max || 5
  return (
    <section className="panel prediction-tracker" id="live-prediction-lab">
      <div className="panel-head">
        <div>
          <p className="eyebrow">LIVE PREDICTION LAB</p>
          <h3>Pin · mark-to-market · rate into RAG</h3>
        </div>
        <div className="panel-head-actions">
          <span className="pred-slots">{openCount}/{max} slots</span>
          <button type="button" className="ghost" disabled={busy || !items.some(i => i.status === 'open')} onClick={onRefresh}>
            {busy ? 'Refreshing…' : 'Refresh prices'}
          </button>
          {canTrack && (
            <button type="button" className="primary pred-track-btn" disabled={busy || openCount >= max} onClick={onTrackHere}>
              {openCount >= max ? 'Slots full' : 'Track this analysis'}
            </button>
          )}
        </div>
      </div>

      <ol className="pred-steps">
        <li><strong>1</strong> Analyze a stock</li>
        <li><strong>2</strong> Track this analysis</li>
        <li><strong>3</strong> Refresh prices later</li>
        <li><strong>4</strong> Rate 1–5 → saves to RAG</li>
      </ol>

      <p className="subtle pred-lede">
        Real pins from your Analyze run — not dummy data. Entry = price when you tracked;
        click <strong>Refresh prices</strong> (or reload the page) to update P&amp;L and the accuracy check.
      </p>

      {!items.length && (
        <div className="pred-empty">
          <p>No pinned predictions yet.</p>
          <p className="subtle">Analyze any stock, then use <em>Track this analysis</em> here or <em>Track prediction</em> near the price.</p>
          {canTrack && (
            <button type="button" className="primary" disabled={busy} onClick={onTrackHere}>Track this analysis</button>
          )}
        </div>
      )}

      {items.length > 0 && (
        <div className="table-wrap pred-table-wrap">
          <table className="pred-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Call</th>
                <th>Entry → Now</th>
                <th>P&amp;L</th>
                <th>Check</th>
                <th>Your rating</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map(item => {
                const acc = accuracyCopy(item)
                const ret = Number(item.return_pct)
                return (
                  <tr key={item.id} className={item.status === 'rated' ? 'is-rated' : ''}>
                    <td className="pred-sym">
                      <button type="button" className="linkish" onClick={() => onAnalyze?.(item.symbol)}>{item.symbol}</button>
                      <span className={`pred-status st-${item.status}`}>{item.status}</span>
                      <span className="pred-meta subtle">Pinned {fmtPinDate(item)}</span>
                      <span className="pred-meta subtle">{fmtRefresh(item)}</span>
                    </td>
                    <td className="pred-call">
                      <span className="pred-stance">{pretty(item.predicted_stance)}</span>
                      <span className="pred-horizon">{(item.predicted_horizon || '').toUpperCase()}</span>
                      <span className="pred-expect">{expectedMove(item.predicted_stance)}</span>
                    </td>
                    <td className="pred-prices">
                      <span>{number.format(item.entry_price)}</span>
                      <span className="pred-arrow" aria-hidden>→</span>
                      <span>{number.format(item.latest_price)}</span>
                    </td>
                    <td className={`pred-pnl ${ret >= 0 ? 'up' : 'down'}`}>
                      {ret >= 0 ? '+' : ''}{number.format(ret)}%
                    </td>
                    <td>
                      <span className={`acc-pill acc-${acc.cls}`} title={item.accuracy?.rule || ''}>
                        {acc.text}
                      </span>
                    </td>
                    <td>
                      {item.status === 'rated' ? (
                        <span className="pred-rated">★ {item.user_rating}/5{item.rag_saved ? ' · RAG' : ''}</span>
                      ) : (
                        <div className="rate-row" role="group" aria-label={`Rate ${item.symbol}`}>
                          {[1, 2, 3, 4, 5].map(n => (
                            <button
                              key={n}
                              type="button"
                              className="ghost rate-btn"
                              disabled={busy}
                              onClick={() => onRate(item.id, n)}
                              title={`Rate ${n}/5 and save outcome to RAG`}
                            >
                              {n}
                            </button>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="pred-actions">
                      {item.status !== 'rated' && (
                        <button
                          type="button"
                          className="ghost pred-remove"
                          disabled={busy}
                          onClick={() => onRemove?.(item.id)}
                          title="Remove from lab"
                        >
                          Remove
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}


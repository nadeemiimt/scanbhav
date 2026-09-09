const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })

function PdfIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M7 3h7l5 5v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z"
        stroke="currentColor"
        strokeWidth="1.5"
      />
      <path d="M14 3v6h6" stroke="currentColor" strokeWidth="1.5" />
      <path
        d="M8 13h8M8 16h6M8 19h4"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  )
}

function modeLabel(pickMode) {
  if (pickMode === 'agent_auto') return 'AI auto-pick'
  if (pickMode === 'curated_list') return 'Curated list'
  return pickMode || 'Session'
}

export function SessionReportsPanel({ sessions = [], selectedId = '', busy = false, onSelect, onDownloadPdf }) {
  if (!sessions.length) {
    return (
      <section className="panel session-reports-panel">
        <div className="panel-head">
          <div>
            <p className="eyebrow">SESSION REPORTS</p>
            <h3>Past autopilot sessions</h3>
          </div>
        </div>
        <p className="subtle">No completed sessions yet. Run an all-day session to generate reports here.</p>
      </section>
    )
  }

  return (
    <section className="panel session-reports-panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">SESSION REPORTS</p>
          <h3>Past autopilot sessions</h3>
        </div>
        <span className="subtle">{sessions.length} session(s)</span>
      </div>
      <p className="subtle">
        Each card shows net P&amp;L, gross profit vs loss, session window, and lessons. Click a row to open the full report.
      </p>
      <ul className="session-report-list">
        {sessions.map(row => {
          const net = row.realized_pnl_inr ?? 0
          const profit = row.gross_profit_inr ?? 0
          const loss = row.gross_loss_inr ?? 0
          const isSelected = selectedId === row.session_id
          return (
            <li key={row.session_id} className={`session-report-card${isSelected ? ' is-selected' : ''}`}>
              <button
                type="button"
                className="session-report-main"
                disabled={!!busy}
                onClick={() => onSelect?.(row.session_id)}
              >
                <div className="session-report-top">
                  <div>
                    <strong>{row.trade_date_ist || '—'}</strong>
                    <span className="subtle"> · {modeLabel(row.pick_mode)}</span>
                  </div>
                  <span className={`session-report-net ${net >= 0 ? 'up' : 'down'}`}>
                    {money.format(net)}
                  </span>
                </div>
                <div className="session-report-highlights">
                  <span className="up">+{money.format(profit)} profit</span>
                  <span className="down">−{money.format(loss)} loss</span>
                  <span className="subtle">
                    {row.wins ?? 0}W / {row.losses ?? 0}L · {row.closed_trades ?? 0} closes
                  </span>
                </div>
                <div className="session-report-meta subtle">
                  <span>{row.started_at_ist || '—'}</span>
                  <span> → </span>
                  <span>{row.stopped_at_ist || '—'}</span>
                  {row.cycle_count > 0 && <span> · {row.cycle_count} cycles</span>}
                </div>
                <code className="session-report-id">{row.session_id}</code>
                {row.postmortem_preview && (
                  <p className="session-report-preview">{row.postmortem_preview}</p>
                )}
                {(row.best_symbol || row.worst_symbol) && (
                  <p className="session-report-symbols subtle">
                    {row.best_symbol && (
                      <>Best <b>{row.best_symbol}</b> {money.format(row.best_pnl_inr || 0)}</>
                    )}
                    {row.worst_symbol && row.worst_symbol !== row.best_symbol && (
                      <> · Worst <b>{row.worst_symbol}</b> {money.format(row.worst_pnl_inr || 0)}</>
                    )}
                  </p>
                )}
              </button>
              <button
                type="button"
                className="ghost session-report-pdf-btn"
                title="Download PDF report"
                disabled={!!busy}
                onClick={e => {
                  e.stopPropagation()
                  onDownloadPdf?.(row.session_id)
                }}
              >
                <PdfIcon />
                <span>PDF</span>
              </button>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

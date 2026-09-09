export const PLATFORM_GAPS = [
  {
    id: 'execution',
    gap: 'No live execution',
    why: 'Research only — no orders, brackets, or trailing stops.',
  },
  {
    id: 'cache',
    gap: 'Delayed / cached data',
    why: '~4-hour cache; polled refresh, not a live feed.',
  },
  {
    id: 'eod',
    gap: 'End-of-day focus',
    why: 'Daily candles — not built for precise intraday entry timing.',
  },
  {
    id: 'heuristic',
    gap: 'Heuristic scores',
    why: 'Conviction and dossier bands are rules-based reads, not proven edge.',
  },
  {
    id: 'alerts',
    gap: 'No alerts',
    why: 'No “price hit S1” or “RSI crossed 70” notifications.',
  },
  {
    id: 'backtest',
    gap: 'Basic backtests',
    why: 'EOD closes and simplified fees — not broker-grade.',
  },
  {
    id: 'genai',
    gap: 'Gen AI desk',
    why: 'Commentary and synthesis — verify against raw Technical Board data.',
  },
]

function cacheNote(dataAsOf, cached) {
  const parts = []
  if (dataAsOf) parts.push(`Price as of ${dataAsOf}`)
  if (cached === true) parts.push('served from cache (use Refresh before acting)')
  if (cached === false) parts.push('fresh fetch')
  return parts.length ? parts.join(' · ') : null
}

export function PlatformLimitationsPanel({
  compact = false,
  defaultOpen = false,
  embedded = false,
  dataAsOf,
  cached,
  className = '',
}) {
  const note = cacheNote(dataAsOf, cached)

  const tableBlock = (
    <>
      <p className="subtle platform-limits-lead">
        Useful for screening and multi-day research (including swing-style reads). Not a trading terminal.
      </p>
      {note && <p className="subtle platform-limits-note">{note}</p>}
      <div className="table-wrap platform-limits-table-wrap">
        <table className="platform-limits-table">
          <thead>
            <tr>
              <th>Gap</th>
              <th>Why it matters</th>
            </tr>
          </thead>
          <tbody>
            {PLATFORM_GAPS.map(row => (
              <tr key={row.id}>
                <td>{row.gap}</td>
                <td>{row.why}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )

  if (embedded) {
    return (
      <div className={`platform-limits platform-limits--embedded ${className}`.trim()}>
        {tableBlock}
      </div>
    )
  }

  if (compact) {
    return (
      <details className={`platform-limits platform-limits--compact ${className}`.trim()} open={defaultOpen}>
        <summary>Platform limits — research desk, not a broker</summary>
        <ul className="platform-limits-list">
          {PLATFORM_GAPS.map(row => (
            <li key={row.id}>
              <strong>{row.gap}</strong> — {row.why}
            </li>
          ))}
        </ul>
        {note && <p className="subtle platform-limits-note">{note}</p>}
      </details>
    )
  }

  return (
    <section className={`panel platform-limits ${className}`.trim()}>
      <details open={defaultOpen}>
        <summary className="platform-limits-summary">
          <div>
            <p className="eyebrow">RESEARCH LIMITS</p>
            <h3 className="platform-limits-title">What this desk is — and is not</h3>
          </div>
          <span className="subtle platform-limits-hint">Expand for full list</span>
        </summary>
        {tableBlock}
      </details>
    </section>
  )
}

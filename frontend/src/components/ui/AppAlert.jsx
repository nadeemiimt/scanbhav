const SEVERITY_LABELS = {
  signal: 'Signal',
  caution: 'Caution',
  warn: 'Warning',
  info: 'Info',
}

export function AppAlert({ severity = 'info', symbol, message, ts, meta }) {
  const label = SEVERITY_LABELS[severity] || 'Alert'
  return (
    <article className={`app-alert app-alert--${severity}`}>
      <div className="app-alert-head">
        <span className="app-alert-badge">{label}</span>
        {symbol && <strong className="app-alert-symbol">{symbol}</strong>}
        {ts && <time className="app-alert-time">{formatTs(ts)}</time>}
      </div>
      <p className="app-alert-message">{message}</p>
      {meta?.composite_score != null && (
        <p className="app-alert-meta subtle">
          Composite {Number(meta.composite_score).toFixed(1)} · {meta.stance || '—'}
        </p>
      )}
    </article>
  )
}

function formatTs(ts) {
  try {
    const d = new Date(ts)
    if (Number.isNaN(d.getTime())) return ts
    return d.toLocaleString('en-IN', { hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'short' })
  } catch {
    return ts
  }
}

export function AppAlertList({ alerts = [], emptyMessage = 'No alerts yet.' }) {
  if (!alerts.length) {
    return <p className="app-alert-empty subtle">{emptyMessage}</p>
  }
  return (
    <div className="app-alert-list">
      {alerts.map(a => (
        <AppAlert
          key={a.id || `${a.symbol}-${a.ts}-${a.message}`}
          severity={a.severity}
          symbol={a.symbol}
          message={a.message}
          ts={a.ts}
          meta={a.meta}
        />
      ))}
    </div>
  )
}

export default AppAlert

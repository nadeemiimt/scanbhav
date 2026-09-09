const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 })

function RulesCard({ title, rules }) {
  if (!rules) return null
  return (
    <article className="trade-plan-rules-card">
      <h4>{title}</h4>
      <dl className="trade-plan-rules-dl">
        <div><dt>Product</dt><dd>{rules.product || rules.style}</dd></div>
        <div><dt>Horizon</dt><dd>{rules.horizon}</dd></div>
        {rules.target_pct != null && (
          <div><dt>Target / Stop</dt><dd>+{rules.target_pct}% / −{rules.stop_pct}%</dd></div>
        )}
        {rules.square_off_ist && (
          <div><dt>Square-off</dt><dd>{rules.square_off_ist} IST</dd></div>
        )}
        {rules.min_composite != null && (
          <div><dt>Min composite</dt><dd>{rules.min_composite}</dd></div>
        )}
        <div><dt>Entry</dt><dd>{rules.entry_strategy}</dd></div>
        <div><dt>Exit</dt><dd>{rules.exit_strategy}</dd></div>
        {rules.reentry && <div><dt>Re-entry</dt><dd>{rules.reentry}</dd></div>}
        {rules.sizing && <div><dt>Sizing</dt><dd>{rules.sizing}</dd></div>}
        {rules.note && <div><dt>Note</dt><dd>{rules.note}</dd></div>}
      </dl>
    </article>
  )
}

function PlanRow({ row }) {
  const plan = row.plan || {}
  const entry = plan.entry || {}
  const exit = plan.exit || {}
  const timing = entry.timing || {}
  const entryPx = entry.entry_price_inr ?? entry.price_inr
  return (
    <tr className={row.decision ? `audit-${row.decision}` : ''}>
      <td><b>{row.symbol || plan.symbol}</b></td>
      <td>{row.decision || (plan.planned ? 'planned' : '—')}</td>
      <td>{row.stance || plan.stance || '—'}</td>
      <td>{row.composite_score ?? plan.composite_score ?? '—'}</td>
      <td>{entryPx != null ? money.format(entryPx) : '—'}</td>
      <td>{exit.stop_price_inr != null ? money.format(exit.stop_price_inr) : `−${exit.stop_pct ?? '—'}%`}</td>
      <td>{exit.target_price_inr != null ? money.format(exit.target_price_inr) : `+${exit.target_pct ?? '—'}%`}</td>
      <td className="subtle">
        {timing.window_label || timing.reason || '—'}
        {timing.allowed === false && ' (wait)'}
        {timing.allowed === true && ' ✓'}
      </td>
      <td className="subtle">{row.reason || row.fit_reason || plan.fit_reason || '—'}</td>
    </tr>
  )
}

export function TradePlanPanel({
  intradayRules,
  swingRules,
  rows,
  loading,
  sourceLabel,
}) {
  return (
    <section className="panel trade-plan-panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">TRADE PLAN</p>
          <h3>Entry &amp; exit strategy</h3>
        </div>
        {sourceLabel && <span className="subtle">{sourceLabel}</span>}
      </div>
      <p className="subtle">
        Intraday autopilot uses MIS with percent targets from fill price. Swing trades use ATR-based levels on the Swing desk.
      </p>

      <div className="trade-plan-rules-grid">
        <RulesCard title="Intraday (MIS autopilot)" rules={intradayRules} />
        <RulesCard title="Swing (multi-day)" rules={swingRules} />
      </div>

      {loading && <p className="subtle">Building plan from live quotes…</p>}

      {!loading && rows.length > 0 && (
        <>
          <p className="eyebrow" style={{ marginTop: 16 }}>PER-SYMBOL PLAN</p>
          <div className="session-audit-table-wrap">
            <table className="session-audit-table trade-plan-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Status</th>
                  <th>Stance</th>
                  <th>Score</th>
                  <th>Entry ₹</th>
                  <th>Stop ₹</th>
                  <th>Target ₹</th>
                  <th>Timing</th>
                  <th>Why</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(row => (
                  <PlanRow key={row.symbol || row.plan?.symbol} row={row} />
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {!loading && rows.length === 0 && (
        <p className="subtle" style={{ marginTop: 12 }}>
          Add stocks above to see planned entry, stop, and target levels.
        </p>
      )}
    </section>
  )
}

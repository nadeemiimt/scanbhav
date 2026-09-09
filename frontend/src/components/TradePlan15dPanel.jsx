const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 })

export function TradePlan15dPanel({ plan, embedded = false }) {
  if (!plan?.ok) return null
  const levels = plan.levels_used || {}
  const body = (
    <>
      <p className="subtle">{plan.plain}</p>
      <div className="trade-plan-15d-grid">
        <article>
          <p className="eyebrow">Buy near</p>
          <p className="trade-plan-15d-price up">{money.format(plan.entry_price)}</p>
          <p className="subtle">Pullback to S1/pivot/ATR zone</p>
        </article>
        <article>
          <p className="eyebrow">Best exit</p>
          <p className="trade-plan-15d-price">{money.format(plan.exit_price)}</p>
          <p className="subtle">+{plan.upside_pct}% vs entry target</p>
        </article>
        <article>
          <p className="eyebrow">Stop</p>
          <p className="trade-plan-15d-price down">{money.format(plan.stop_price || 0)}</p>
          <p className="subtle">−{plan.downside_pct}% risk vs entry</p>
        </article>
        <article>
          <p className="eyebrow">Now</p>
          <p className="trade-plan-15d-price">{money.format(plan.current_price)}</p>
          <p className="subtle">15d hist {plan.return_15d_hist_pct != null ? `${plan.return_15d_hist_pct}%` : '—'}</p>
        </article>
      </div>
      <ul className="reason-list compact" style={{ marginTop: 12 }}>
        <li>Pivot S1 ₹{levels.s1 ?? '—'} · R1 ₹{levels.r1 ?? '—'}</li>
        <li>Stance {plan.stance} · composite {plan.composite_score ?? '—'}</li>
      </ul>
      <p className="subtle">{plan.disclaimer}</p>
    </>
  )

  if (embedded) {
    return <div className="trade-plan-15d-panel trade-plan-embedded">{body}</div>
  }

  return (
    <section className="panel trade-plan-15d-panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">15-DAY PLAN</p>
          <h3>Entry &amp; exit levels</h3>
        </div>
        <span className="subtle">{plan.horizon_days}-day horizon</span>
      </div>
      {body}
    </section>
  )
}

const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 })
const pct = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 1, signDisplay: 'always' })

function fmtPct(v) {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return `${pct.format(Number(v))}%`
}

export function tradePlan7dHint(plan) {
  if (!plan?.ok) return 'Pullback and recovery scenarios'
  const fc = plan.forecast_7d || {}
  const band = plan.pullback_band || {}
  const parts = []
  if (fc.target_price != null) parts.push(`Target ${money.format(fc.target_price)}`)
  if (band.low != null && band.high != null) {
    parts.push(`Pullback ${money.format(band.low)}–${money.format(band.high)}`)
  }
  return parts.join(' · ') || plan.plain?.slice(0, 80) || '7-day scenario map'
}

export function TradePlan7dPanel({ plan, embedded = false, includeTriggers = true }) {
  if (!plan?.ok) return null
  const fc = plan.forecast_7d || {}
  const band = plan.pullback_band || {}
  const paths = plan.paths || []
  const triggers = plan.triggers || []

  const body = (
    <>
      <p className="subtle">{plan.plain}</p>

      {plan.overbought_note && (
        <p className="subtle trade-plan-7d-warning">{plan.overbought_note}</p>
      )}

      <div className="trade-plan-15d-grid trade-plan-7d-grid">
        <article>
          <p className="eyebrow">7d target</p>
          <p className="trade-plan-15d-price up">{money.format(fc.target_price || 0)}</p>
          <p className="subtle">{fmtPct(fc.expected_return_pct)} expected</p>
        </article>
        <article>
          <p className="eyebrow">7d band</p>
          <p className="trade-plan-15d-price">{money.format(fc.price_band_low || 0)}</p>
          <p className="subtle">to {money.format(fc.price_band_high || 0)}</p>
        </article>
        <article>
          <p className="eyebrow">Pullback zone</p>
          <p className="trade-plan-15d-price down">{money.format(band.low || 0)}</p>
          <p className="subtle">
            {band.high ? `– ${money.format(band.high)} · ${fmtPct(band.pct_low)} to ${fmtPct(band.pct_high)}` : '—'}
          </p>
        </article>
        <article>
          <p className="eyebrow">Now</p>
          <p className="trade-plan-15d-price">{money.format(plan.current_price)}</p>
          <p className="subtle">
            RSI {plan.rsi_14 != null ? plan.rsi_14.toFixed(1) : '—'}
            {plan.atr_pct != null ? ` · ATR ${plan.atr_pct.toFixed(1)}%` : ''}
          </p>
        </article>
      </div>

      {paths.length > 0 && (
        <div className="trade-plan-7d-paths">
          {paths.map(path => (
            <article key={path.id} className="trade-plan-7d-path">
              <h4>{path.title}</h4>
              <p className="subtle">{path.likelihood_note}</p>
              <ol className="reason-list compact">
                {(path.steps || []).map(step => (
                  <li key={step.phase}>
                    <strong>{step.phase}:</strong> {step.detail}
                  </li>
                ))}
              </ol>
            </article>
          ))}
        </div>
      )}

      {includeTriggers && triggers.length > 0 && (
        <>
          <p className="eyebrow" style={{ marginTop: 14 }}>Daily triggers</p>
          <ul className="reason-list compact">
            {triggers.map(t => (
              <li key={`${t.kind}-${t.label}`}>
                <strong>{t.label}:</strong> {t.level}
              </li>
            ))}
          </ul>
        </>
      )}

      {(plan.zones || []).length > 0 && (
        <>
          <p className="eyebrow" style={{ marginTop: 14 }}>Key levels</p>
          <div className="table-wrap">
            <table className="trade-plan-7d-levels">
              <thead>
                <tr>
                  <th>Level</th>
                  <th>Price</th>
                  <th>vs now</th>
                  <th>Role</th>
                </tr>
              </thead>
              <tbody>
                {plan.zones.map(z => (
                  <tr key={z.label}>
                    <td>{z.label}</td>
                    <td>{money.format(z.price)}</td>
                    <td className={z.pct_from_now > 0 ? 'up' : z.pct_from_now < 0 ? 'down' : ''}>
                      {fmtPct(z.pct_from_now)}
                    </td>
                    <td>{z.role}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <p className="subtle">{plan.disclaimer}</p>
    </>
  )

  if (embedded) {
    return <div className="trade-plan-7d-panel trade-plan-embedded">{body}</div>
  }

  return (
    <section className="panel trade-plan-7d-panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">7-DAY SWING MAP</p>
          <h3>Pullback &amp; recovery scenarios</h3>
        </div>
        <span className="subtle">{plan.horizon_days}-day horizon</span>
      </div>
      {body}
    </section>
  )
}

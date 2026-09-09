import { number, pretty } from '../../utils/analysisFormatters'

function Row({ label, value, hint }) {
  if (value == null || value === '' || value === '—') return null
  return (
    <div className="ext-factor-row">
      <span className="ext-factor-label">{label}</span>
      <span className="ext-factor-value">{value}</span>
      {hint && <span className="subtle ext-factor-hint">{hint}</span>}
    </div>
  )
}

function Section({ title, children }) {
  if (!children) return null
  return (
    <article className="ext-factor-section">
      <h4>{title}</h4>
      {children}
    </article>
  )
}

export function ExtendedFactorsPanel({ extended, ratings }) {
  if (!extended) return null
  const ind = extended.indicators || {}
  const ich = ind.ichimoku || {}
  const fib = ind.fibonacci || {}
  const pat = extended.patterns || {}
  const div = extended.divergence || {}
  const fund = extended.fundamentals || {}
  const qs = fund.quality_scores || {}
  const opt = extended.options || {}
  const india = extended.india || {}
  const hold = india.shareholding || {}
  const intra = extended.intraday || {}
  const mc = extended.market_context || {}
  const adj = ratings?.extended_adjustment || extended.ratings_blended?.extended_adjustment

  return (
    <section className="panel extended-factors-panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">EXTENDED FACTORS</p>
          <h3>Ichimoku · patterns · quality · India · options · regime</h3>
        </div>
        <span className="subtle">Coverage {extended.coverage?.pct ?? '—'}%</span>
      </div>

      {adj && (
        <p className="ext-adjust-banner">
          Composite adjusted {adj.delta >= 0 ? '+' : ''}{adj.delta} from base {adj.base_composite}
          {(adj.reasons || []).length > 0 && `: ${adj.reasons.slice(0, 3).join(' ')}`}
        </p>
      )}

      <div className="ext-factor-grid">
        <Section title="Ichimoku & channels">
          <Row label="Cloud" value={ich.price_vs_cloud} hint={`TK ${ich.tenkan_kijun_cross || ''}`} />
          <Row label="CMF(20)" value={ind.cmf?.cmf_20} hint={ind.cmf?.bias} />
          <Row label="Parabolic SAR" value={ind.parabolic_sar?.direction} />
          <Row label="Keltner" value={ind.keltner?.price_position} />
          <Row label="Donchian" value={ind.donchian?.breakout || 'inside'} />
          <Row label="Hull MA" value={ind.price_vs_hull} />
        </Section>

        <Section title="Fibonacci">
          <Row label="Nearest" value={fib.nearest_retracement ? `${fib.nearest_retracement} @ ${number.format(fib.nearest_level)}` : null} />
          <Row label="Swing leg" value={fib.trend_leg} />
        </Section>

        <Section title="Patterns & divergence">
          <Row label="Patterns" value={(pat.active_patterns || []).join(', ') || 'none'} hint={pat.composite_bias} />
          <Row label="Divergence" value={div.composite_signal} hint={div.headline} />
        </Section>

        <Section title="Fundamentals & quality">
          <Row label="Quality score" value={qs.composite_quality} hint={qs.composite_label} />
          <Row label="Piotroski" value={qs.piotroski ? `${qs.piotroski.score}/9` : null} />
          <Row label="Altman Z" value={qs.altman?.z_score} hint={qs.altman?.zone} />
          <Row label="Interest coverage" value={fund.debt_quality?.interest_coverage} />
          <Row label="Net debt/EBITDA" value={fund.debt_quality?.net_debt_ebitda} />
          <Row label="Analyst target" value={fund.analyst_consensus?.target_mean} hint={fund.analyst_consensus?.upside_pct != null ? `${fund.analyst_consensus.upside_pct}% upside` : ''} />
        </Section>

        <Section title="India & options">
          <Row label="Promoter %" value={hold.promoter_pct} />
          <Row label="FII holding %" value={hold.fii_pct} />
          <Row label="Pledge %" value={hold.pledge_pct} />
          <Row label="PCR (OI)" value={opt.pcr_oi} hint={opt.pcr_bias} />
          <Row label="Max pain" value={opt.max_pain} />
          <Row label="Avg IV" value={opt.avg_iv_pct != null ? `${opt.avg_iv_pct}%` : null} />
        </Section>

        <Section title="Context">
          <Row label="Regime" value={extended.regime?.regime?.regime} />
          <Row label="VIX pctile" value={extended.regime?.vix?.percentile_1y} hint={extended.regime?.vix?.label} />
          <Row label="Sector RS" value={mc.sector_relative_strength?.headline?.plain || mc.sector_relative_strength?.status} />
          <Row label="Intraday 1h" value={intra.status === 'ok' ? `RSI ${intra.rsi_14}, ${intra.price_vs_vwap} VWAP` : intra.status} />
          <Row label="Insider" value={extended.insider?.headline} />
          <Row label="Analyst bias" value={extended.analyst?.upgrade_bias} hint={extended.analyst?.recommendation} />
        </Section>
      </div>

      <p className="subtle" style={{ marginTop: 12 }}>
        Extended factors blend into composite score and dossier conviction. Educational only — verify NSE/Yahoo feeds before acting.
      </p>
    </section>
  )
}

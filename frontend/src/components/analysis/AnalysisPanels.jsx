import { useState } from 'react'
import { number, pretty, tipFor } from '../../utils/analysisFormatters'

export function InvestorPanel({ investors }) {
  if (!investors?.length) return null
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">FAMOUS INVESTOR LENSES</p>
          <h3>Would their pattern buy, hold, or sell?</h3>
        </div>
      </div>
      <p className="subtle" style={{ marginBottom: 14 }}>Simulated style matching from technicals + fundamentals — not real recommendations from these investors.</p>
      <div className="investor-grid">
        {investors.map(inv => (
          <article key={inv.id} className={`investor-card stance-${inv.stance}`}>
            <p className="eyebrow">{inv.style}</p>
            <h4>{inv.name}</h4>
            <p className="investor-label">{inv.label}</p>
            <p className="subtle">{inv.pattern}</p>
            <ul className="reason-list compact">
              {(inv.reasons || []).slice(0, 4).map((r, i) => <li key={i}>{r}</li>)}
            </ul>
            <p className="subtle">{inv.disclaimer}</p>
          </article>
        ))}
      </div>
    </section>
  )
}

export function DeepDossierPanel({ dossier }) {
  const [techFilter, setTechFilter] = useState('all')
  if (!dossier) return null
  const conviction = dossier.conviction || {}
  const moat = dossier.competitive || {}
  const radar = dossier.signal_radar || {}
  const critical = dossier.critical_signals || {}
  const distortion = critical.price_distortion || {}
  const history = critical.price_history || {}
  const barriers = critical.psychological_barriers || {}
  const policy = critical.government_policy || {}
  const foundation = critical.corporate_foundation || {}
  const decoded = dossier.decoded || {}
  const scenarios = dossier.scenario_lab || {}
  const board = dossier.technical_board || []
  const groups = ['all', ...Object.keys(dossier.technical_groups || {})]
  const filtered = techFilter === 'all' ? board : board.filter(r => r.group === techFilter)
  const coverage = dossier.truth_thermometer?.data_coverage_score

  return (
    <div className="dossier-stack">
      <section className="panel dossier-hero">
        <div className="panel-head dossier-hero-head">
          <div className="dossier-brand">
            <span className="dossier-mark" aria-hidden>SA</span>
            <div>
              <p className="eyebrow">DEEP MARKET DOSSIER</p>
              <h3>Stock in &amp; out · applied signals · competitive edge</h3>
            </div>
          </div>
          <span className="subtle dossier-meta">{dossier.parameters_applied || board.length} parameters applied</span>
        </div>
        <p className="subtle dossier-disclaimer">{dossier.disclaimer}</p>

        <div className="conviction-grid">
          <article className="conviction-meter">
            <p className="eyebrow">CONVICTION ENSEMBLE</p>
            <div className="conviction-ring" style={{ '--conv': `${conviction.conviction_score || 0}%` }}>
              <strong>{conviction.conviction_score ?? '—'}</strong>
              <span>score</span>
            </div>
            <p className="conviction-band">{conviction.band}</p>
            <p>{conviction.plain_english}</p>
            <p className="subtle">Confidence {conviction.confidence ?? '—'} · {conviction.forecast_note}</p>
          </article>
          <article>
            <p className="eyebrow">FACTOR BREAKDOWN</p>
            <div className="factor-bars">
              {(conviction.factors || []).map(f => (
                <div key={f.id} className="factor-bar-row">
                  <div className="factor-bar-label">
                    <span>{f.label}</span>
                    <span>{f.score} · w{(f.weight * 100).toFixed(0)}%</span>
                  </div>
                  <div className="factor-bar-track">
                    <div className="factor-bar-fill" style={{ width: `${Math.max(4, f.score)}%` }} />
                  </div>
                </div>
              ))}
            </div>
            {coverage != null && (
              <p className="subtle" style={{ marginTop: 12 }}>
                Truth thermometer (data coverage): <b>{coverage}</b>/100 — {dossier.truth_thermometer?.note}
              </p>
            )}
          </article>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="eyebrow">STOCK DECODED</p>
            <h3>{decoded.headline || 'Plain-English briefing'}</h3>
          </div>
        </div>
        <div className="decoded-grid">
          {(decoded.facts || []).map((fact, i) => (
            <article key={i} className="decoded-card">
              <h4>{fact.title}</h4>
              <p>{fact.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="eyebrow">COMPETITIVE EDGE</p>
            <h3>Advantage vs disadvantage · {moat.industry || 'peers'}</h3>
          </div>
          <span className={`moat-pill moat-${moat.moat_label?.replace(/\s+/g, '-') || 'contested'}`}>
            Moat {moat.moat_score ?? '—'} · {moat.moat_label || 'n/a'}
          </span>
        </div>
        <div className="moat-grid">
          <div>
            <h4 className="up">Advantages</h4>
            <ul className="reason-list">
              {(moat.advantages || []).length
                ? moat.advantages.map((x, i) => <li key={i}>{x}</li>)
                : <li className="subtle">No clear advantage flagged from available peers/fundamentals.</li>}
            </ul>
          </div>
          <div>
            <h4 className="down">Disadvantages</h4>
            <ul className="reason-list">
              {(moat.disadvantages || []).length
                ? moat.disadvantages.map((x, i) => <li key={i}>{x}</li>)
                : <li className="subtle">No clear disadvantage flagged.</li>}
            </ul>
          </div>
        </div>
        {(moat.comparisons || []).length > 0 && (
          <div className="table-wrap" style={{ marginTop: 14 }}>
            <table>
              <thead>
                <tr><th>Metric</th><th>You</th><th>Peer median</th><th>Edge</th></tr>
              </thead>
              <tbody>
                {moat.comparisons.map((c, i) => (
                  <tr key={i}>
                    <td>{c.metric}</td>
                    <td>{typeof c.you === 'number' ? number.format(c.you) : c.you}</td>
                    <td>{typeof c.peer_median === 'number' ? number.format(c.peer_median) : c.peer_median}</td>
                    <td className={`edge-${c.edge}`}>{c.edge}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {(moat.peers || []).length > 0 && (
          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table>
              <thead>
                <tr><th>Peer</th><th>Name</th><th>P/E</th><th>P/B</th><th>Chg%</th></tr>
              </thead>
              <tbody>
                {moat.peers.map((p, i) => (
                  <tr key={i}>
                    <td>{p.symbol}</td>
                    <td>{p.name}</td>
                    <td>{p.trailing_pe != null ? number.format(p.trailing_pe) : '—'}</td>
                    <td>{p.price_to_book != null ? number.format(p.price_to_book) : '—'}</td>
                    <td className={p.change_pct >= 0 ? 'up' : 'down'}>
                      {p.change_pct != null ? number.format(p.change_pct) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="subtle">{moat.disclaimer}</p>
      </section>

      <section className="panel critical-signals-panel">
        <div className="panel-head">
          <div>
            <p className="eyebrow">CRITICAL SIGNALS</p>
            <h3>Price distortion · 5y history · barriers · policy · foundation</h3>
          </div>
          <span className="subtle">
            Inflation {distortion.inflation_risk || '—'} · Deflation {distortion.deflation_risk || '—'} ·
            {' '}5y pumps {history.pump_count_5y ?? '—'} · dumps {history.dump_count_5y ?? '—'} ·
            {' '}pairs {history.pump_and_dump_count_5y ?? '—'} · Foundation {foundation.foundation_exposure || '—'}
          </span>
        </div>

        <div className="critical-signals-grid">
          <article className="critical-card">
            <p className="eyebrow">ARTIFICIAL INFLATION / DEFLATION</p>
            <p>{distortion.primary_read || distortion.plain_english || 'No distortion scan yet — run Analyze.'}</p>
            {(distortion.signals || []).length > 0 && (
              <ul className="reason-list compact">
                {(distortion.signals || []).slice(0, 5).map((s, i) => (
                  <li key={i}>
                    <span className={`risk-pill risk-${s.severity}`}>{s.severity}</span>
                    {' '}
                    {s.plain_english}
                  </li>
                ))}
              </ul>
            )}
            {history.recent_pump_dump_emphasis && (
              <p className="critical-emphasis">{history.recent_pump_dump_emphasis}</p>
            )}
          </article>

          <article className="critical-card">
            <p className="eyebrow">5-YEAR PUMP / DUMP HISTORY</p>
            <p>{history.plain_english || history.headline || 'Run Analyze to scan ~5 years of daily candles.'}</p>
            {(history.episodes || []).length > 0 && (
              <ul className="reason-list compact">
                {(history.episodes || []).slice(-6).reverse().map((ep, i) => (
                  <li key={i}>
                    <span className={`risk-pill risk-${ep.severity || 'moderate'}`}>{ep.type?.replace(/_/g, ' ')}</span>
                    {' '}
                    {ep.plain_english || `${ep.date || ep.dump_date}: ${ep.move_pct ?? ep.dump_pct}%`}
                  </li>
                ))}
              </ul>
            )}
          </article>

          <article className="critical-card">
            <p className="eyebrow">PSYCHOLOGICAL BARRIERS</p>
            <p>{barriers.headline || 'No nearby round-number / 52w / pivot barriers flagged.'}</p>
            {(barriers.barriers || []).length > 0 && (
              <ul className="reason-list compact">
                {(barriers.barriers || []).slice(0, 5).map((b, i) => (
                  <li key={i}>
                    <strong>{b.label}</strong> @ {b.level} ({b.distance_pct > 0 ? '+' : ''}{b.distance_pct}%)
                    {' — '}
                    {b.note}
                  </li>
                ))}
              </ul>
            )}
          </article>

          <article className="critical-card">
            <p className="eyebrow">GOVERNMENT POLICY</p>
            <p>{policy.plain_english || 'No policy headlines tagged in latest news sweep.'}</p>
            {(policy.sector_watch_items || []).length > 0 && (
              <ul className="reason-list compact">
                {(policy.sector_watch_items || []).slice(0, 4).map((w, i) => (
                  <li key={i}>Sector watch: {w}</li>
                ))}
              </ul>
            )}
            {(policy.headlines || []).length > 0 && (
              <ul className="reason-list compact news-headlines" style={{ marginTop: 8 }}>
                {(policy.headlines || []).slice(0, 4).map((h, i) => (
                  <li key={i}>
                    <span className="news-tag tag-regulation-policy">{h.catalyst_label || 'Policy'}</span>
                    {' '}
                    {h.url ? <a href={h.url} target="_blank" rel="noreferrer">{h.title}</a> : h.title}
                  </li>
                ))}
              </ul>
            )}
          </article>

          <article className="critical-card">
            <p className="eyebrow">CORPORATE FOUNDATION</p>
            <p>{foundation.plain_english || 'Officer / group-structure scan runs after profile + news load.'}</p>
            {foundation.ceo?.name && (
              <p className="subtle">Key executive: {foundation.ceo.name}{foundation.ceo.title ? ` · ${foundation.ceo.title}` : ''}</p>
            )}
            {(foundation.governance_headlines || []).length > 0 && (
              <ul className="reason-list compact news-headlines">
                {(foundation.governance_headlines || []).slice(0, 4).map((h, i) => (
                  <li key={i}>
                    <span className={`risk-pill risk-${h.severity || 'moderate'}`}>{h.severity || 'flag'}</span>
                    {' '}
                    {h.url ? <a href={h.url} target="_blank" rel="noreferrer">{h.title}</a> : h.title}
                  </li>
                ))}
              </ul>
            )}
            {(foundation.associated_company_mentions || []).length > 0 && (
              <ul className="reason-list compact">
                {(foundation.associated_company_mentions || []).slice(0, 3).map((m, i) => (
                  <li key={i}>{m}</li>
                ))}
              </ul>
            )}
          </article>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="eyebrow">SIGNAL RADAR</p>
            <h3>Green flags · red flags</h3>
          </div>
          <span className="subtle">Balance {radar.balance > 0 ? '+' : ''}{radar.balance ?? 0}</span>
        </div>
        <div className="moat-grid">
          <div>
            <h4 className="up">Green flags</h4>
            <ul className="reason-list">
              {(radar.green_flags || []).map((x, i) => <li key={i}>{x}</li>)}
            </ul>
          </div>
          <div>
            <h4 className="down">Red flags</h4>
            <ul className="reason-list">
              {(radar.red_flags || []).map((x, i) => <li key={i}>{x}</li>)}
            </ul>
          </div>
        </div>
      </section>

      <section className="panel scenario-lab-panel">
        <div className="panel-head">
          <div>
            <p className="eyebrow">SCENARIO STRESS LAB</p>
            <h3 className="dossier-section-title">
              What-if market research
              {scenarios.atr_pct_context != null && (
                <span className="dossier-title-meta"> · ATR context {scenarios.atr_pct_context}%</span>
              )}
            </h3>
          </div>
        </div>
        <div className="scenario-grid">
          {(scenarios.scenarios || []).map((s, i) => (
            <article key={i} className={`scenario-card bias-${s.bias}`}>
              <span className={`bias-chip bias-${s.bias}`}>{s.bias}</span>
              <h4>{s.title}</h4>
              <p className="scenario-impact">{s.impact}</p>
              <p className="subtle scenario-why">{s.why}</p>
            </article>
          ))}
        </div>
        {scenarios.disclaimer && <p className="subtle scenario-disclaimer">{scenarios.disclaimer}</p>}
      </section>

      <section className="panel tech-board-panel">
        <div className="panel-head">
          <div>
            <p className="eyebrow">TECHNICAL BOARD</p>
            <h3 className="dossier-section-title">Live board · signal + plain English</h3>
          </div>
          <span className="subtle">{filtered.length} rows</span>
        </div>
        <div className="tech-filter-row" role="tablist" aria-label="Technical groups">
          {groups.map(g => (
            <button
              key={g}
              type="button"
              role="tab"
              aria-selected={techFilter === g}
              className={`ghost tech-filter ${techFilter === g ? 'active' : ''}`}
              onClick={() => setTechFilter(g)}
            >
              {g === 'all' ? 'All' : g.charAt(0).toUpperCase() + g.slice(1)}
            </button>
          ))}
        </div>
        <div className="table-wrap tech-board-wrap">
          <table className="tech-board-table">
            <thead>
              <tr>
                <th>Parameter</th>
                <th>Group</th>
                <th>Value</th>
                <th>Signal</th>
                <th>What’s applied</th>
                <th>Plain English</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(row => (
                <tr key={row.key} className={`sig-${row.signal}`}>
                  <td className="tb-param"><strong>{row.label}</strong></td>
                  <td className="tb-group">{row.group}</td>
                  <td className="tb-value">
                    {row.value == null || row.value === ''
                      ? '—'
                      : `${typeof row.value === 'number' ? number.format(row.value) : row.value}${row.unit || ''}`}
                  </td>
                  <td className="tb-signal"><span className={`sig-pill sig-${row.signal}`}>{row.signal}</span></td>
                  <td className="tb-applied">{row.applied}</td>
                  <td className="tb-plain">{row.plain_english}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

export function TaSnapshot({ tech, guide, learnMode = false }) {
  if (!tech) return null
  const ma = tech.moving_averages || {}
  const mom = tech.momentum || {}
  const vol = tech.volatility || {}
  const trend = tech.trend || {}
  const volume = tech.volume || {}
  const levels = tech.levels || {}
  const M = learnMode ? TeachableMetric : Metric
  const extra = learnMode ? { learnMode: true } : {}
  return (
    <>
      <section className="metrics">
        <M tip={tipFor(guide, 'rsi_14')} label="RSI 14" value={mom.rsi_14} {...extra} />
        <M tip={tipFor(guide, 'macd_hist')} label="MACD hist" value={mom.macd_hist} {...extra} />
        <M tip={tipFor(guide, 'stoch_k')} label="Stoch %K" value={mom.stoch_k} {...extra} />
        <M tip={tipFor(guide, 'cci_20')} label="CCI 20" value={mom.cci_20} {...extra} />
        <M tip={tipFor(guide, 'williams_r')} label="Williams %R" value={mom.williams_r} {...extra} />
        <M tip={tipFor(guide, 'roc_12')} label="ROC 12" value={mom.roc_12} suffix="%" {...extra} />
        <M tip={tipFor(guide, 'mfi_14')} label="MFI 14" value={mom.mfi_14} {...extra} />
        <M tip={tipFor(guide, 'adx_14')} label="ADX 14" value={trend.adx_14} {...extra} />
        <M tip={tipFor(guide, 'atr_pct')} label="ATR %" value={vol.atr_pct} suffix="%" {...extra} />
        <M tip={tipFor(guide, 'bb_pct_b')} label="BB %B" value={vol.bb_pct_b} {...extra} />
        <M tip={tipFor(guide, 'rvol')} label="RVOL" value={volume.rvol} {...extra} />
        <M tip={tipFor(guide, 'price_vs_sma_200_pct')} label="vs SMA200" value={ma.price_vs_sma_200_pct} suffix="%" {...extra} />
      </section>

      <section className="panel">
        <div className="panel-head"><div><p className="eyebrow">MOVING AVERAGES</p><h3>SMA / EMA stack</h3></div></div>
        <section className="metrics">
          <M tip={tipFor(guide, 'sma_20')} label="SMA 20" value={ma.sma_20} {...extra} />
          <M tip={tipFor(guide, 'sma_50')} label="SMA 50" value={ma.sma_50} {...extra} />
          <M tip={tipFor(guide, 'sma_100')} label="SMA 100" value={ma.sma_100} {...extra} />
          <M tip={tipFor(guide, 'sma_200')} label="SMA 200" value={ma.sma_200} {...extra} />
          <M tip={tipFor(guide, 'ema_9')} label="EMA 9" value={ma.ema_9} {...extra} />
          <M tip={tipFor(guide, 'ema_21')} label="EMA 21" value={ma.ema_21} {...extra} />
          <M tip={tipFor(guide, 'ema_50')} label="EMA 50" value={ma.ema_50} {...extra} />
          <M tip={tipFor(guide, 'ema_200')} label="EMA 200" value={ma.ema_200} {...extra} />
          <M tip={tipFor(guide, 'golden_cross')} label="Golden cross" value={ma.golden_cross ? 1 : 0} {...extra} />
          <M tip={tipFor(guide, 'death_cross')} label="Death cross" value={ma.death_cross ? 1 : 0} {...extra} />
          <M tip={tipFor(guide, 'ema_stack_bullish')} label="EMA stack" value={ma.ema_stack_bullish ? 1 : 0} {...extra} />
          <M tip={tipFor(guide, 'supertrend_dir')} label="Supertrend" value={trend.supertrend_dir} {...extra} />
        </section>
      </section>

      <section className="panel">
        <div className="panel-head"><div><p className="eyebrow">LEVELS & VOLUME</p><h3>Pivots · 52w · flow</h3></div></div>
        <section className="metrics">
          <M tip={tipFor(guide, 'pivot')} label="Pivot" value={levels.pivot} {...extra} />
          <M tip={tipFor(guide, 'r1')} label="R1" value={levels.r1} {...extra} />
          <M tip={tipFor(guide, 's1')} label="S1" value={levels.s1} {...extra} />
          <M tip={tipFor(guide, 'r2')} label="R2" value={levels.r2} {...extra} />
          <M tip={tipFor(guide, 's2')} label="S2" value={levels.s2} {...extra} />
          <M tip={tipFor(guide, 'high_52w')} label="52w high" value={levels.high_52w} {...extra} />
          <M tip={tipFor(guide, 'low_52w')} label="52w low" value={levels.low_52w} {...extra} />
          <M tip={tipFor(guide, 'dist_from_52w_high_pct')} label="vs 52w high" value={levels.dist_from_52w_high_pct} suffix="%" {...extra} />
          <M tip={tipFor(guide, 'obv')} label="OBV" value={volume.obv} {...extra} />
          <M tip={tipFor(guide, 'obv_slope_20')} label="OBV slope" value={volume.obv_slope_20} {...extra} />
          <M tip={tipFor(guide, 'plus_di')} label="+DI" value={trend.plus_di} {...extra} />
          <M tip={tipFor(guide, 'minus_di')} label="−DI" value={trend.minus_di} {...extra} />
        </section>
      </section>
    </>
  )
}

function Metric({ label, value, suffix = '', tip }) {
  return (
    <article className="metric">
      <p>{label}{tip ? ' ⓘ' : ''}</p>
      <strong>{value === undefined || value === null ? '—' : `${number.format(value)}${suffix}`}</strong>
      {tip && <span className="metric-tip" role="tooltip">{tip}</span>}
    </article>
  )
}

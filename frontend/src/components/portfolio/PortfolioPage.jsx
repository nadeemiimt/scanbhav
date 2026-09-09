import { useState } from 'react'
import { APP_NAME } from '../../brand'
import { apiGet, apiPost } from '../../lib/apiClient'
import { money, number } from '../../utils/analysisFormatters'
import useConfirmDialog from '../../hooks/useConfirmDialog'

export function PortfolioPage({ portfolio, setPortfolio, setError, onAnalyze }) {
  const { confirm, dialog } = useConfirmDialog()
  const [busy, setBusy] = useState(false)
  const [sellPreview, setSellPreview] = useState(null)
  const [sellAllResult, setSellAllResult] = useState(null)
  const settings = portfolio?.settings || {}
  const holdings = portfolio?.holdings || []
  const alerts = portfolio?.alerts || []
  const totals = portfolio?.totals || {}

  async function saveSettings(patch) {
    setBusy(true)
    try {
      const result = await apiPost('/api/portfolio/settings', patch)
      setPortfolio(result)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function refreshAlerts() {
    setBusy(true)
    try {
      const result = await apiPost('/api/portfolio/alerts/refresh', {})
      if (result.portfolio) setPortfolio(result.portfolio)
      else setPortfolio(await apiGet('/api/portfolio'))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function previewSell(holdingId) {
    setBusy(true)
    setSellPreview(null)
    try {
      const result = await apiPost('/api/portfolio/sell', { holding_id: holdingId, preview_only: true })
      setSellPreview(result.preview)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function confirmSell(holdingId) {
    setBusy(true)
    try {
      const result = await apiPost('/api/portfolio/sell', { holding_id: holdingId, preview_only: false })
      setPortfolio(result.portfolio)
      setSellPreview(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function sellAll() {
    const ok = await confirm({
      title: 'Sell all positions',
      message: 'Sell all open paper positions at latest marks? This updates your local portfolio ledger.',
      confirmLabel: 'Sell all',
      cancelLabel: 'Cancel',
      variant: 'danger',
    })
    if (!ok) return
    setBusy(true)
    setSellAllResult(null)
    try {
      const result = await apiPost('/api/portfolio/sell-all', {})
      setPortfolio(result.portfolio)
      setSellAllResult(result)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
    <section className="content-page">
      <p className="eyebrow">Portfolio</p>
      <h2>Local paper desk</h2>
      <p>
        Purchases are stored in <code>{portfolio?.files?.txt || 'data/portfolio/holdings.txt'}</code>.
        Intraday sells use broker intraday charges; delivery/MF use delivery schedules. Tax uses Indian STCG 20% / LTCG 12.5% (₹1.25L exemption) for equity; debt MF uses your slab.
      </p>

      <div className="hero-stats portfolio-stats">
        <article className="hero-stat"><p>Positions</p><strong>{totals.positions ?? 0}</strong></article>
        <article className="hero-stat"><p>Invested</p><strong>{money.format(totals.invested || 0)}</strong></article>
        <article className="hero-stat"><p>Mark value</p><strong>{totals.market_value != null ? money.format(totals.market_value) : '—'}</strong></article>
        <article className="hero-stat">
          <p>Unrealized</p>
          <strong className={(totals.unrealized_pnl || 0) >= 0 ? 'up' : 'down'}>
            {totals.unrealized_pnl != null ? money.format(totals.unrealized_pnl) : '—'}
          </strong>
        </article>
      </div>

      <section className="panel" style={{ marginTop: 18 }}>
        <div className="panel-head"><div><p className="eyebrow">SETTINGS</p><h3>Broker & tax bracket</h3></div></div>
        <div className="buy-grid">
          <label>
            Broker (fee schedule)
            <select
              value={settings.broker || 'zerodha'}
              disabled={busy}
              onChange={e => saveSettings({ broker: e.target.value })}
            >
              {(portfolio?.brokers || [{ id: 'zerodha', label: 'Zerodha' }, { id: 'groww', label: 'Groww' }]).map(b => (
                <option key={b.id} value={b.id}>{b.label}</option>
              ))}
            </select>
          </label>
          <label>
            Income-tax slab (debt MF / reference)
            <select
              value={settings.tax_bracket_id || 'slab_30'}
              disabled={busy}
              onChange={e => saveSettings({ tax_bracket_id: e.target.value })}
            >
              {(portfolio?.tax_brackets || []).map(b => (
                <option key={b.id} value={b.id}>{b.label}</option>
              ))}
            </select>
          </label>
          <button className="ghost" disabled={busy} onClick={refreshAlerts}>Refresh TA alerts</button>
          <button className="primary" disabled={busy || !holdings.length} onClick={sellAll}>Sell all · show net proceeds</button>
        </div>
        <p className="subtle" style={{ marginTop: 10 }}>{portfolio?.tax_rules?.note}</p>
      </section>

      {alerts.length > 0 && (
        <section className="panel">
          <div className="panel-head"><div><p className="eyebrow">ALERTS</p><h3>Buy more / sell signals</h3></div><span>{alerts.length}</span></div>
          <div className="alert-list">
            {alerts.map((a, i) => (
              <article key={i} className={`alert-item level-${a.level}`}>
                <b>{pretty(a.level)}</b>
                <span>{a.symbol}</span>
                <p>{a.message}</p>
                <button className="ghost" onClick={() => onAnalyze(a.symbol)}>Analyze</button>
              </article>
            ))}
          </div>
        </section>
      )}

      {sellAllResult && (
        <section className="panel">
          <div className="panel-head"><div><p className="eyebrow">SELL ALL RESULT</p><h3>Net amount you get</h3></div></div>
          <div className="hero-stats">
            <article className="hero-stat"><p>Sold</p><strong>{sellAllResult.sold_count}</strong></article>
            <article className="hero-stat"><p>Net to you</p><strong className="up">{money.format(sellAllResult.total_net_you_get || 0)}</strong></article>
            <article className="hero-stat"><p>Tax</p><strong>{money.format(sellAllResult.total_tax || 0)}</strong></article>
            <article className="hero-stat"><p>Broker deductions</p><strong>{money.format(sellAllResult.total_broker_deductions || 0)}</strong></article>
          </div>
        </section>
      )}

      {sellPreview && (
        <section className="panel">
          <div className="panel-head">
            <div><p className="eyebrow">SELL PREVIEW</p><h3>{sellPreview.symbol} · {sellPreview.intraday ? 'Intraday' : 'Delivery/MF'}</h3></div>
            <button className="ghost" onClick={() => setSellPreview(null)}>Close</button>
          </div>
          <div className="metrics">
            <Metric label="Gross P&L" value={sellPreview.gross_pnl} />
            <Metric label="Broker deductions" value={sellPreview.deduction_total} />
            <Metric label="P&L after charges" value={sellPreview.pnl_after_charges} />
            <Metric label={`Tax (${sellPreview.tax?.regime})`} value={sellPreview.tax?.tax} />
            <Metric label="P&L after tax" value={sellPreview.pnl_after_tax} />
            <Metric label="You receive" value={sellPreview.net_amount_you_get} />
          </div>
          <p className="subtle">
            Sell charges: brokerage ₹{sellPreview.sell_charges?.brokerage} · STT ₹{sellPreview.sell_charges?.stt} ·
            GST ₹{sellPreview.sell_charges?.gst} · DP ₹{sellPreview.sell_charges?.dp_charges} · total ₹{sellPreview.sell_charges?.total}
            {sellPreview.intraday ? ' (intraday schedule)' : ' (delivery/MF schedule)'}.
          </p>
          <button className="primary" style={{ marginTop: 12 }} disabled={busy} onClick={() => confirmSell(sellPreview.holding_id)}>Confirm sell</button>
        </section>
      )}

      <section className="panel">
        <div className="panel-head"><div><p className="eyebrow">HOLDINGS</p><h3>Open positions</h3></div></div>
        {!holdings.length && <p className="subtle">No holdings yet. Analyze a stock and click Purchase.</p>}
        {holdings.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Symbol</th><th>Type</th><th>Qty</th><th>Avg</th><th>Mark</th><th>P&L</th><th>Days</th><th></th>
                </tr>
              </thead>
              <tbody>
                {holdings.map(h => (
                  <tr key={h.id}>
                    <td className="clickable" onClick={() => onAnalyze(h.symbol)}>{h.symbol}</td>
                    <td>{h.asset_type}</td>
                    <td>{h.quantity}</td>
                    <td>{number.format(h.avg_price)}</td>
                    <td>{h.mark_price != null ? number.format(h.mark_price) : '—'}</td>
                    <td className={(h.unrealized_pnl || 0) >= 0 ? 'up' : 'down'}>
                      {h.unrealized_pnl != null ? number.format(h.unrealized_pnl) : '—'}
                    </td>
                    <td>{h.holding_days}</td>
                    <td><button className="ghost" disabled={busy} onClick={() => previewSell(h.id)}>Sell</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {(portfolio?.closed || []).length > 0 && (
        <section className="panel">
          <div className="panel-head"><div><p className="eyebrow">CLOSED</p><h3>Recent sales</h3></div></div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Symbol</th><th>Qty</th><th>Buy</th><th>Sell</th><th>Deductions</th><th>Tax</th><th>Net</th><th>After-tax P&L</th></tr>
              </thead>
              <tbody>
                {[...(portfolio.closed || [])].reverse().slice(0, 20).map((c, i) => (
                  <tr key={i}>
                    <td>{c.symbol}</td>
                    <td>{c.quantity}</td>
                    <td>{number.format(c.buy_price)}</td>
                    <td>{number.format(c.sell_price)}</td>
                    <td>{number.format(c.deduction_total)}</td>
                    <td>{number.format(c.tax?.tax)}</td>
                    <td>{number.format(c.net_amount_you_get)}</td>
                    <td className={(c.pnl_after_tax || 0) >= 0 ? 'up' : 'down'}>{number.format(c.pnl_after_tax)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </section>
    {dialog}
    </>
  )
}

function MarketsPage({ onAnalyze, go }) {
  const picks = [
    { symbol: 'RELIANCE.NSE', name: 'Reliance Industries', blurb: 'Energy-to-retail bellwether' },
    { symbol: 'TCS.NSE', name: 'Tata Consultancy', blurb: 'IT services quality compounder' },
    { symbol: 'HDFCBANK.NSE', name: 'HDFC Bank', blurb: 'Private banking benchmark' },
    { symbol: 'INFY.NSE', name: 'Infosys', blurb: 'Digital services pulse check' },
    { symbol: 'ICICIBANK.NSE', name: 'ICICI Bank', blurb: 'Franchise + growth mix' },
    { symbol: 'SBIN.NSE', name: 'State Bank of India', blurb: 'PSU banking proxy' },
  ]
  return (
    <section className="content-page">
      <p className="eyebrow">Markets</p>
      <h2>Desk watchlist</h2>
      <p>Jump into liquid names the {APP_NAME} universe tracks every day. Open any card for a full 1D→5Y technical rating.</p>
      <div className="content-grid">
        {picks.map(item => (
          <article className="content-card" key={item.symbol}>
            <h4>{item.symbol}</h4>
            <p><b>{item.name}</b></p>
            <p>{item.blurb}</p>
            <button className="primary" style={{ marginTop: 12 }} onClick={() => onAnalyze(item.symbol)}>Analyze</button>
          </article>
        ))}
      </div>
      <p style={{ marginTop: 22 }}>
        Prefer a broad ranking?{' '}
        <button className="ghost" onClick={() => go('multi')}>Open the multi-stock screener</button>
      </p>
    </section>
  )
}

function MethodPage() {
  return (
    <section className="content-page">
      <p className="eyebrow">Method</p>
      <h2>How {APP_NAME} scores a stock</h2>
      <p>
        Every rating is built from transparent technical inputs — not a black-box tip. Hover any parameter on the Analyze page
        for what it is and why it is useful.
      </p>
      <h3>Core indicator stack</h3>
      <ul>
        <li>Trend: SMA 20/50/100/200, EMA 9/12/21/26/50/200, golden/death cross, Supertrend, pivots</li>
        <li>Momentum: RSI 7/14, MACD 12/26/9, Stochastic, CCI, Williams %R, ROC, MFI</li>
        <li>Volatility: Bollinger Bands 20×2, ATR 14</li>
        <li>Strength: ADX / +DI / −DI</li>
        <li>Participation: volume SMA, relative volume, OBV slope</li>
      </ul>
      <h3>Portfolio math</h3>
      <p>Paper buys/sells apply approximate Zerodha or Groww charges. Equity STCG 20% / LTCG 12.5% with ₹1.25L exemption; debt MF uses your selected slab. Educational estimates only.</p>
    </section>
  )
}

function AboutPage({ go }) {
  return (
    <section className="content-page">
      <p className="eyebrow">About</p>
      <h2>{APP_NAME}</h2>
      <p>
        {APP_NAME} is your local neural research desk — scan the bhav and score Indian equities and mutual funds,
        with investor-style lenses and a paper portfolio desk.
      </p>
      <div className="content-grid">
        <article className="content-card">
          <h4>Analyze</h4>
          <p>Full indicator readout, charts, and horizon ratings.</p>
          <button className="primary" style={{ marginTop: 12 }} onClick={() => go('single')}>Open Analyze</button>
        </article>
        <article className="content-card">
          <h4>Portfolio</h4>
          <p>Buy/sell locally with fees, tax, and TA alerts.</p>
          <button className="primary" style={{ marginTop: 12 }} onClick={() => go('portfolio')}>Open Portfolio</button>
        </article>
        <article className="content-card">
          <h4>Local first</h4>
          <p>API + UI on your machine. Educational use only — not investment advice.</p>
        </article>
      </div>
    </section>
  )
}

function pretty(value) {
  return String(value || '').replaceAll('_', ' ')
}

function tipFor(guide, key) {
  const g = guide?.[key]
  if (!g) return null
  return `${g.what}\n\nWhy useful: ${g.why}`
}

function TaSnapshot({ tech, guide }) {
  if (!tech) return null
  const ma = tech.moving_averages || {}
  const mom = tech.momentum || {}
  const vol = tech.volatility || {}
  const trend = tech.trend || {}
  const volume = tech.volume || {}
  const levels = tech.levels || {}
  return (
    <>
      <section className="metrics">
        <Metric tip={tipFor(guide, 'rsi_14')} label="RSI 14" value={mom.rsi_14} />
        <Metric tip={tipFor(guide, 'macd_hist')} label="MACD hist" value={mom.macd_hist} />
        <Metric tip={tipFor(guide, 'stoch_k')} label="Stoch %K" value={mom.stoch_k} />
        <Metric tip={tipFor(guide, 'cci_20')} label="CCI 20" value={mom.cci_20} />
        <Metric tip={tipFor(guide, 'williams_r')} label="Williams %R" value={mom.williams_r} />
        <Metric tip={tipFor(guide, 'roc_12')} label="ROC 12" value={mom.roc_12} suffix="%" />
        <Metric tip={tipFor(guide, 'mfi_14')} label="MFI 14" value={mom.mfi_14} />
        <Metric tip={tipFor(guide, 'adx_14')} label="ADX 14" value={trend.adx_14} />
        <Metric tip={tipFor(guide, 'atr_pct')} label="ATR %" value={vol.atr_pct} suffix="%" />
        <Metric tip={tipFor(guide, 'bb_pct_b')} label="BB %B" value={vol.bb_pct_b} />
        <Metric tip={tipFor(guide, 'rvol')} label="RVOL" value={volume.rvol} />
        <Metric tip={tipFor(guide, 'price_vs_sma_200_pct')} label="vs SMA200" value={ma.price_vs_sma_200_pct} suffix="%" />
      </section>

      <section className="panel">
        <div className="panel-head"><div><p className="eyebrow">MOVING AVERAGES</p><h3>SMA / EMA stack</h3></div></div>
        <section className="metrics">
          <Metric tip={tipFor(guide, 'sma_20')} label="SMA 20" value={ma.sma_20} />
          <Metric tip={tipFor(guide, 'sma_50')} label="SMA 50" value={ma.sma_50} />
          <Metric tip={tipFor(guide, 'sma_100')} label="SMA 100" value={ma.sma_100} />
          <Metric tip={tipFor(guide, 'sma_200')} label="SMA 200" value={ma.sma_200} />
          <Metric tip={tipFor(guide, 'ema_9')} label="EMA 9" value={ma.ema_9} />
          <Metric tip={tipFor(guide, 'ema_21')} label="EMA 21" value={ma.ema_21} />
          <Metric tip={tipFor(guide, 'ema_50')} label="EMA 50" value={ma.ema_50} />
          <Metric tip={tipFor(guide, 'ema_200')} label="EMA 200" value={ma.ema_200} />
          <Metric tip={tipFor(guide, 'golden_cross')} label="Golden cross" value={ma.golden_cross ? 1 : 0} />
          <Metric tip={tipFor(guide, 'death_cross')} label="Death cross" value={ma.death_cross ? 1 : 0} />
          <Metric tip={tipFor(guide, 'ema_stack_bullish')} label="EMA stack" value={ma.ema_stack_bullish ? 1 : 0} />
          <Metric tip={tipFor(guide, 'supertrend_dir')} label="Supertrend" value={trend.supertrend_dir} />
        </section>
      </section>

      <section className="panel">
        <div className="panel-head"><div><p className="eyebrow">LEVELS & VOLUME</p><h3>Pivots · 52w · flow</h3></div></div>
        <section className="metrics">
          <Metric tip={tipFor(guide, 'pivot')} label="Pivot" value={levels.pivot} />
          <Metric tip={tipFor(guide, 'r1')} label="R1" value={levels.r1} />
          <Metric tip={tipFor(guide, 's1')} label="S1" value={levels.s1} />
          <Metric tip={tipFor(guide, 'r2')} label="R2" value={levels.r2} />
          <Metric tip={tipFor(guide, 's2')} label="S2" value={levels.s2} />
          <Metric tip={tipFor(guide, 'high_52w')} label="52w high" value={levels.high_52w} />
          <Metric tip={tipFor(guide, 'low_52w')} label="52w low" value={levels.low_52w} />
          <Metric tip={tipFor(guide, 'dist_from_52w_high_pct')} label="vs 52w high" value={levels.dist_from_52w_high_pct} suffix="%" />
          <Metric tip={tipFor(guide, 'obv')} label="OBV" value={volume.obv} />
          <Metric tip={tipFor(guide, 'obv_slope_20')} label="OBV slope" value={volume.obv_slope_20} />
          <Metric tip={tipFor(guide, 'plus_di')} label="+DI" value={trend.plus_di} />
          <Metric tip={tipFor(guide, 'minus_di')} label="−DI" value={trend.minus_di} />
        </section>
      </section>
    </>
  )
}

function Metric({ label, value, suffix = '', tip }) {
  return (
    <article className="metric" title={tip || undefined}>
      <p>{label}{tip ? ' ⓘ' : ''}</p>
      <strong>{value === undefined || value === null ? '—' : `${number.format(value)}${suffix}`}</strong>
      {tip && <span className="metric-tip">{tip}</span>}
    </article>
  )
}
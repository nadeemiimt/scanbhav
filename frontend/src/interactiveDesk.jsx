import { useEffect, useMemo, useRef, useState } from 'react'
import { apiGet, apiPost } from './lib/apiClient'
import { loadStore, saveStore } from './lib/storage'

const number = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 })
const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })

export { number, money }

const WIZARD_KEY = 'scanBhavWizard'
const WATCHLIST_KEY = 'scanBhavWatchlist'

const WIZARD_GOALS = [
  { id: 'grow', label: 'Grow wealth' },
  { id: 'income', label: 'Steady income' },
  { id: 'learn', label: 'Learn markets' },
]

const WIZARD_RISKS = [
  { id: 'conservative', label: 'Conservative' },
  { id: 'moderate', label: 'Moderate' },
  { id: 'aggressive', label: 'Aggressive' },
]

const STARTER_SYMBOLS = [
  'RELIANCE.NSE',
  'TCS.NSE',
  'HDFCBANK.NSE',
  'INFY.NSE',
  'NIFTYBEES.NSE',
]

const EVENT_FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'earnings', label: 'Earnings' },
  { id: 'risk', label: 'Risk' },
  { id: 'rates', label: 'Rates' },
]

function useDebouncedEffect(effect, deps, delay) {
  useEffect(() => {
    const timer = setTimeout(effect, delay)
    return () => clearTimeout(timer)
  }, deps)
}

export function GuidedWizard({ open, onClose, onAnalyze, onEnableBeginner }) {
  const [step, setStep] = useState(0)
  const [answers, setAnswers] = useState(() => loadStore(WIZARD_KEY, {
    goal: 'grow',
    risk: 'moderate',
    symbol: STARTER_SYMBOLS[0],
  }))

  useEffect(() => {
    if (open) {
      const saved = loadStore(WIZARD_KEY, answers)
      setAnswers(saved)
      setStep(0)
    }
  }, [open])

  useEffect(() => {
    saveStore(WIZARD_KEY, answers)
  }, [answers])

  if (!open) return null

  const steps = ['Goal', 'Risk', 'Symbol', 'Summary']
  const goalLabel = WIZARD_GOALS.find(g => g.id === answers.goal)?.label || answers.goal
  const riskLabel = WIZARD_RISKS.find(r => r.id === answers.risk)?.label || answers.risk

  function finish() {
    onEnableBeginner?.()
    onAnalyze?.(answers.symbol)
    onClose?.()
  }

  return (
    <div className="genai-modal-backdrop" role="dialog" aria-modal="true" aria-label="Guided setup">
      <div className="genai-modal wizard-modal">
        <section className="panel wizard-panel">
          <div className="wizard-header">
            <div>
              <p className="eyebrow">GET STARTED</p>
              <h3>Guided setup</h3>
            </div>
            <button type="button" className="ghost" onClick={onClose}>Close</button>
          </div>

          <div className="wizard-rail" aria-hidden>
            {steps.map((label, i) => (
              <span key={label} className={`wizard-rail-seg${i <= step ? ' on' : ''}`} />
            ))}
          </div>

          <div className="wizard-tabs" role="tablist">
            {steps.map((label, i) => (
              <button
                key={label}
                type="button"
                role="tab"
                aria-selected={i === step}
                className={`wizard-tab${i === step ? ' active' : ''}${i < step ? ' done' : ''}`}
                onClick={() => setStep(i)}
              >
                <span className="wizard-tab-num">{i + 1}</span>
                <span className="wizard-tab-label">{label}</span>
              </button>
            ))}
          </div>

          <div className="wizard-body">
            {step === 0 && (
              <>
                <p className="wizard-prompt">What is your primary goal?</p>
                <div className="wizard-choice-grid">
                  {WIZARD_GOALS.map(g => (
                    <button
                      key={g.id}
                      type="button"
                      className={`wizard-choice${answers.goal === g.id ? ' active' : ''}`}
                      onClick={() => setAnswers(a => ({ ...a, goal: g.id }))}
                    >
                      {g.label}
                    </button>
                  ))}
                </div>
              </>
            )}

            {step === 1 && (
              <>
                <p className="wizard-prompt">How much risk feels comfortable?</p>
                <div className="wizard-choice-grid">
                  {WIZARD_RISKS.map(r => (
                    <button
                      key={r.id}
                      type="button"
                      className={`wizard-choice${answers.risk === r.id ? ' active' : ''}`}
                      onClick={() => setAnswers(a => ({ ...a, risk: r.id }))}
                    >
                      {r.label}
                    </button>
                  ))}
                </div>
              </>
            )}

            {step === 2 && (
              <>
                <p className="wizard-prompt">Pick a starter symbol to analyze</p>
                <div className="wizard-choice-grid symbols">
                  {STARTER_SYMBOLS.map(sym => (
                    <button
                      key={sym}
                      type="button"
                      className={`wizard-choice${answers.symbol === sym ? ' active' : ''}`}
                      onClick={() => setAnswers(a => ({ ...a, symbol: sym }))}
                    >
                      {sym.replace('.NSE', '')}
                    </button>
                  ))}
                </div>
              </>
            )}

            {step === 3 && (
              <>
                <p className="wizard-prompt">Ready to analyze</p>
                <ul className="reason-list compact wizard-summary">
                  <li>Goal: <strong>{goalLabel}</strong></li>
                  <li>Risk: <strong>{riskLabel}</strong></li>
                  <li>Symbol: <strong>{answers.symbol}</strong></li>
                </ul>
                <p className="subtle">We will enable beginner-friendly hints and run your first analysis.</p>
              </>
            )}
          </div>

          <div className="wizard-footer">
            <button type="button" className="ghost" disabled={step === 0} onClick={() => setStep(s => s - 1)}>Back</button>
            {step < 3 ? (
              <button type="button" className="primary" onClick={() => setStep(s => s + 1)}>Next</button>
            ) : (
              <button type="button" className="primary" onClick={finish}>
                Analyze {answers.symbol.replace('.NSE', '')}
              </button>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}

export function LearnModeToggle({ learnMode, onToggle }) {
  return (
    <label className="refresh-toggle">
      <input type="checkbox" checked={learnMode} onChange={e => onToggle(e.target.checked)} />
      Learn mode
    </label>
  )
}

export function TeachableMetric({ label, value, suffix = '', tip, learnMode }) {
  const [open, setOpen] = useState(false)
  const showTip = learnMode && tip
  const display = value === undefined || value === null ? '—' : `${number.format(value)}${suffix}`

  return (
    <article className={`metric teachable${showTip && open ? ' is-open' : ''}`}>
      <button
        type="button"
        className="linkish"
        style={{ textAlign: 'left', width: '100%' }}
        onClick={() => showTip && setOpen(v => !v)}
        disabled={!showTip}
      >
        <p style={{ margin: 0 }}>{label}{showTip ? ' · tap to learn' : ''}</p>
        <strong>{display}</strong>
      </button>
      {showTip && open && <div className="teach-bubble">{tip}</div>}
    </article>
  )
}

export function AlertsBell({ provider, onAnalyze }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [alerts, setAlerts] = useState([])
  const [priceAbove, setPriceAbove] = useState('')
  const [priceBelow, setPriceBelow] = useState('')
  const [symbols, setSymbols] = useState([])
  const rootRef = useRef(null)

  useEffect(() => {
    if (open) setSymbols(loadStore(WATCHLIST_KEY, []))
  }, [open])

  useEffect(() => {
    if (!open) return undefined
    function onPointerDown(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    function onKeyDown(e) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  async function scan() {
    if (!symbols.length) {
      setAlerts([])
      return
    }
    setBusy(true)
    try {
      const rules = {
        rsi_above: 70,
        rsi_below: 30,
        supertrend_flip: true,
      }
      if (priceAbove.trim()) rules.price_above = Number(priceAbove)
      if (priceBelow.trim()) rules.price_below = Number(priceBelow)

      const data = await apiPost('/api/desk/watch-scan', { symbols, provider, rules })
      setAlerts(data.alerts || [])
    } catch {
      setAlerts([])
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="alerts-bell" ref={rootRef}>
      <button type="button" className="ghost" onClick={() => setOpen(v => !v)} aria-expanded={open}>
        Alerts
        {alerts.length > 0 && <span className="alerts-badge">{alerts.length}</span>}
      </button>
      {open && (
        <div className="alerts-panel panel">
          <div className="panel-head">
            <div><p className="eyebrow">WATCHLIST</p><h3>Rule scan</h3></div>
            <span className="subtle">{symbols.length} symbols</span>
          </div>
          <div className="buy-grid">
            <label>
              Price above
              <input type="number" value={priceAbove} onChange={e => setPriceAbove(e.target.value)} placeholder="Optional" />
            </label>
            <label>
              Price below
              <input type="number" value={priceBelow} onChange={e => setPriceBelow(e.target.value)} placeholder="Optional" />
            </label>
          </div>
          <button type="button" className="primary" disabled={busy || !symbols.length} onClick={scan}>
            {busy ? 'Scanning…' : 'Scan now'}
          </button>
          {!symbols.length && <p className="subtle">Add symbols to your watchlist first.</p>}
          {alerts.length > 0 && (
            <ul className="reason-list compact">
              {alerts.map((a, i) => (
                <li key={`${a.symbol}-${i}`}>
                  <button type="button" className="linkish" onClick={() => onAnalyze?.(a.symbol)}>
                    {a.message}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {symbols.length > 0 && !busy && alerts.length === 0 && (
            <p className="subtle">No alerts matched current rules.</p>
          )}
        </div>
      )}
    </div>
  )
}

export function LevelsDesk({ levels, session }) {
  const [hoverBucket, setHoverBucket] = useState(null)

  if (!session?.available) return null

  const profile = session.volume_profile || []
  const maxIntensity = Math.max(...profile.map(b => b.intensity || 0), 0.001)

  return (
    <section className="panel levels-desk">
      <div className="panel-head">
        <div><p className="eyebrow">SESSION</p><h3>Levels & volume</h3></div>
        {session.plain && <span className="subtle">{session.plain}</span>}
      </div>

      <div className="metrics">
        <article className="metric">
          <p>Prior high</p>
          <strong>{session.prior_high != null ? number.format(session.prior_high) : '—'}</strong>
        </article>
        <article className="metric">
          <p>Prior low</p>
          <strong>{session.prior_low != null ? number.format(session.prior_low) : '—'}</strong>
        </article>
        <article className="metric">
          <p>Gap %</p>
          <strong>{session.gap_pct != null ? `${number.format(session.gap_pct)}%` : '—'}</strong>
        </article>
        <article className="metric">
          <p>Gap filled</p>
          <strong>{session.gap_filled ? 'Yes' : 'No'}</strong>
        </article>
        <article className="metric">
          <p>Pivot</p>
          <strong>{levels?.pivot != null ? number.format(levels.pivot) : '—'}</strong>
        </article>
        <article className="metric">
          <p>R1 / S1</p>
          <strong>
            {levels?.r1 != null ? number.format(levels.r1) : '—'}
            {' / '}
            {levels?.s1 != null ? number.format(levels.s1) : '—'}
          </strong>
        </article>
        <article className="metric">
          <p>POC</p>
          <strong>{session.poc != null ? number.format(session.poc) : '—'}</strong>
        </article>
      </div>

      {profile.length > 0 && (
        <div className="levels-profile">
          <p className="eyebrow">Volume profile</p>
          {profile.map((b, i) => (
            <div
              key={i}
              className="levels-bar-row"
              onMouseEnter={() => setHoverBucket(b)}
              onMouseLeave={() => setHoverBucket(null)}
              title={`${number.format(b.price_mid)} · vol ${number.format(b.volume)}`}
            >
              <span className="subtle">{number.format(b.price_mid)}</span>
              <div className="levels-bar-track">
                <div
                  className="levels-bar-fill"
                  style={{ width: `${((b.intensity || 0) / maxIntensity) * 100}%` }}
                />
              </div>
            </div>
          ))}
          {hoverBucket && (
            <p className="subtle">Mid price {number.format(hoverBucket.price_mid)} · intensity {number.format((hoverBucket.intensity || 0) * 100)}%</p>
          )}
        </div>
      )}
    </section>
  )
}

export function BacktestPanel({ symbol, provider, onError }) {
  const [strategy, setStrategy] = useState('sma_cross')
  const [capital, setCapital] = useState(100000)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)

  async function run() {
    if (!symbol) return onError?.('Analyze a symbol first.')
    onError?.('')
    setBusy(true)
    try {
      const data = await apiPost('/api/desk/backtest', {
        symbol, provider, strategy, capital: Number(capital),
      })
      setResult(data)
    } catch (err) {
      onError?.(err.message)
    } finally {
      setBusy(false)
    }
  }

  const curve = (result?.equity_curve || []).slice(-10)

  return (
    <section className="panel backtest-panel">
      <div className="panel-head">
        <div><p className="eyebrow">BACKTEST</p><h3>Rule strategies</h3></div>
        {symbol && <span className="subtle">{symbol}</span>}
      </div>
      <div className="buy-grid">
        <label>
          Strategy
          <select value={strategy} onChange={e => setStrategy(e.target.value)}>
            <option value="sma_cross">SMA cross</option>
            <option value="rsi_reversion">RSI reversion</option>
            <option value="trend_follow">Trend follow</option>
          </select>
        </label>
        <label>
          Capital
          <input type="number" min={1000} value={capital} onChange={e => setCapital(e.target.value)} />
        </label>
      </div>
      <button type="button" className="primary" disabled={busy || !symbol} onClick={run}>
        {busy ? 'Running…' : 'Run backtest'}
      </button>
      {result && (
        <>
          <div className="metrics">
            <article className="metric">
              <p>Return</p>
              <strong className={result.return_pct >= 0 ? 'up' : 'down'}>{number.format(result.return_pct)}%</strong>
            </article>
            <article className="metric">
              <p>Max drawdown</p>
              <strong>{number.format(result.max_drawdown_pct)}%</strong>
            </article>
            <article className="metric">
              <p>Win rate</p>
              <strong>{result.win_rate_pct != null ? `${number.format(result.win_rate_pct)}%` : '—'}</strong>
            </article>
          </div>
          {result.plain && <p className="subtle">{result.plain}</p>}
          {curve.length > 0 && (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Date</th><th>Equity</th><th>In market</th></tr></thead>
                <tbody>
                  {curve.map(row => (
                    <tr key={row.date}>
                      <td>{row.date}</td>
                      <td>{money.format(row.equity)}</td>
                      <td>{row.in_market ? 'Yes' : 'No'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  )
}

export function SipCalculator({ onError }) {
  const [monthly, setMonthly] = useState(5000)
  const [years, setYears] = useState(10)
  const [expectedReturn, setExpectedReturn] = useState(12)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)

  async function calc() {
    onError?.('')
    setBusy(true)
    try {
      const data = await apiPost('/api/desk/sip', {
        monthly: Number(monthly),
        years: Number(years),
        expected_annual_return_pct: Number(expectedReturn),
      })
      setResult(data)
    } catch (err) {
      onError?.(err.message)
    } finally {
      setBusy(false)
    }
  }

  useDebouncedEffect(() => {
    if (Number(monthly) >= 100 && Number(years) >= 0.5) calc()
  }, [monthly, years, expectedReturn], 400)

  return (
    <section className="panel sip-calc">
      <div className="panel-head">
        <div><p className="eyebrow">SIP</p><h3>Projection calculator</h3></div>
      </div>
      <div className="buy-grid">
        <label>
          Monthly (INR)
          <input type="number" min={100} value={monthly} onChange={e => setMonthly(e.target.value)} />
        </label>
        <label>
          Years
          <input type="number" min={0.5} step={0.5} value={years} onChange={e => setYears(e.target.value)} />
        </label>
        <label>
          Expected return %
          <input type="number" step={0.5} value={expectedReturn} onChange={e => setExpectedReturn(e.target.value)} />
        </label>
      </div>
      <button type="button" className="ghost" disabled={busy} onClick={calc}>
        {busy ? 'Calculating…' : 'Recalculate'}
      </button>
      {result && (
        <div className="metrics">
          <article className="metric">
            <p>Invested</p>
            <strong>{money.format(result.invested)}</strong>
          </article>
          <article className="metric">
            <p>Projected</p>
            <strong>{money.format(result.projected_value)}</strong>
          </article>
          <article className="metric">
            <p>Gain</p>
            <strong className={result.gain >= 0 ? 'up' : 'down'}>{money.format(result.gain)}</strong>
          </article>
        </div>
      )}
      {result?.plain && <p className="subtle">{result.plain}</p>}
    </section>
  )
}

export function BreadthStrip({ breadth }) {
  const above = breadth?.above_sma200_pct
  const positive = breadth?.positive_horizon_pct

  return (
    <section className="panel breadth-strip">
      <div className="panel-head">
        <div><p className="eyebrow">BREADTH</p><h3>Market pulse</h3></div>
        {breadth?.plain && <span className="subtle">{breadth.plain}</span>}
      </div>
      <div className="buy-grid">
        <label>
          Above SMA200
          <div className="breadth-bar-track">
            <div className="breadth-bar-fill" style={{ width: `${above ?? 0}%` }} />
          </div>
          <span className="subtle">{above != null ? `${number.format(above)}%` : '—'}</span>
        </label>
        <label>
          Positive horizon
          <div className="breadth-bar-track">
            <div className="breadth-bar-fill" style={{ width: `${positive ?? 0}%` }} />
          </div>
          <span className="subtle">{positive != null ? `${number.format(positive)}%` : '—'}</span>
        </label>
      </div>
    </section>
  )
}

function computePortfolioHeat(portfolio) {
  if (portfolio?.summary?.positions?.length) {
    return portfolio.summary.positions.map(p => ({
      symbol: p.symbol,
      weight_pct: p.weight_pct ?? 0,
      market_value: p.market_value,
      hot: (p.weight_pct ?? 0) >= 25,
    }))
  }

  const holdings = portfolio?.holdings || []
  const rows = holdings.map(h => {
    const qty = Number(h.quantity || 0)
    const px = Number(h.mark_price ?? h.current_price ?? h.avg_price ?? 0)
    return {
      symbol: h.symbol,
      market_value: qty * px,
    }
  }).filter(r => r.market_value > 0)

  const total = rows.reduce((s, r) => s + r.market_value, 0)
    || Number(portfolio?.totals?.market_value || portfolio?.summary?.total_value || 0)

  return rows.map(r => {
    const weight_pct = total > 0 ? (r.market_value / total) * 100 : 0
    return {
      ...r,
      weight_pct,
      hot: weight_pct >= 25,
    }
  }).sort((a, b) => b.weight_pct - a.weight_pct)
}

export function PortfolioHeatCard({ portfolio }) {
  const positions = useMemo(() => computePortfolioHeat(portfolio), [portfolio])
  if (!positions.length) return null

  return (
    <section className="panel heat-card">
      <div className="panel-head">
        <div><p className="eyebrow">CONCENTRATION</p><h3>Portfolio heat</h3></div>
        <span className="subtle">{positions.length} positions</span>
      </div>
      <ul className="reason-list compact">
        {positions.map(p => (
          <li key={p.symbol} className={p.hot ? 'hot' : ''}>
            <strong>{p.symbol}</strong>
            {' · '}
            {number.format(p.weight_pct)}%
            {p.market_value != null && (
              <span className="subtle"> · {money.format(p.market_value)}</span>
            )}
            {p.hot && <span className="subtle"> · above 25%</span>}
          </li>
        ))}
      </ul>
    </section>
  )
}

function mergeCalendarItems(events, news) {
  const items = []
  for (const ev of events?.items || []) {
    items.push({
      id: `ev-${ev.title}-${ev.when}`,
      tag: (ev.tag || ev.label || 'general').toLowerCase(),
      kind: ev.kind || 'event',
      title: ev.title,
      when: ev.when || '',
      url: ev.url,
    })
  }
  for (const h of news?.headlines || []) {
    items.push({
      id: `news-${h.title}-${h.published || h.date}`,
      tag: (h.catalyst_tag || 'general').toLowerCase(),
      kind: 'news',
      title: h.title,
      when: h.published || h.date || '',
      url: h.url,
    })
  }
  return items.sort((a, b) => String(b.when).localeCompare(String(a.when)))
}

function matchesEventFilter(item, filter) {
  if (filter === 'all') return true
  if (filter === 'earnings') return item.tag.includes('earning')
  if (filter === 'risk') return item.tag === 'risk' || item.kind === 'risk'
  if (filter === 'rates') return item.tag === 'rates' || item.tag === 'regulation'
  return true
}

export function EventCalendar({ events, news }) {
  const [filter, setFilter] = useState('all')
  const merged = useMemo(() => mergeCalendarItems(events, news), [events, news])
  const visible = merged.filter(item => matchesEventFilter(item, filter))

  if (!merged.length) return null

  return (
    <section className="panel event-calendar">
      <div className="panel-head">
        <div><p className="eyebrow">CALENDAR</p><h3>Events & headlines</h3></div>
        <span className="subtle">{visible.length} shown</span>
      </div>
      <div className="wizard-chips">
        {EVENT_FILTERS.map(f => (
          <button
            key={f.id}
            type="button"
            className={`ghost desk-tool-chip${filter === f.id ? ' active' : ''}`}
            onClick={() => setFilter(f.id)}
          >
            {f.label}
          </button>
        ))}
      </div>
      <ul className="reason-list compact">
        {visible.map(item => (
          <li key={item.id}>
            <span className="eyebrow">{item.tag}</span>
            {item.url ? (
              <a href={item.url} target="_blank" rel="noreferrer">{item.title}</a>
            ) : (
              item.title
            )}
            {item.when && <span className="subtle"> · {item.when}</span>}
          </li>
        ))}
      </ul>
    </section>
  )
}

export function InteractiveShell({
  children,
  title,
  eyebrow,
  defaultOpen = true,
  hint,
  open: openProp,
  onOpenChange,
}) {
  const [internalOpen, setInternalOpen] = useState(defaultOpen)
  const controlled = openProp !== undefined
  const open = controlled ? openProp : internalOpen

  function setOpen(next) {
    const value = typeof next === 'function' ? next(open) : next
    if (!controlled) setInternalOpen(value)
    onOpenChange?.(value)
  }

  return (
    <section className={`panel interactive-shell${open ? ' is-open' : ''}`}>
      <button
        type="button"
        className="shell-toggle"
        onClick={() => setOpen(v => !v)}
        aria-expanded={open}
      >
        <div className="shell-toggle-copy">
          {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
          <h3>{title}</h3>
          {!open && hint ? <p className="subtle shell-hint">{hint}</p> : null}
        </div>
        <span className="shell-toggle-action">{open ? 'Collapse' : 'Expand'}</span>
      </button>
      {open ? <div className="interactive-shell-body">{children}</div> : null}
    </section>
  )
}

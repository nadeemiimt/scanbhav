import { useCallback, useEffect, useRef, useState } from 'react'
import { PlatformLimitationsPanel } from './components/analysis/PlatformLimitations'
import { SwingMiniChart } from './components/swing/SwingMiniChart'
import {
  SWING_TRADES_KEY,
  SWING_WATCHLIST_KEY,
  appendJournalEntry,
  daysHeld,
  exportSwingBook,
  exportSwingBookCsv,
  isDuplicatePlan,
  loadBrokerPrefs,
  loadSwingAlerts,
  saveBrokerPrefs,
  saveSwingAlerts,
} from './components/swing/swingStorage'
import { useSymbolSearch } from './hooks/useSymbolSearch'
import { apiGet, apiPost } from './lib/apiClient'
import { loadStore, saveStore } from './lib/storage'

const number = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 })
const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })

export { SWING_TRADES_KEY, SWING_WATCHLIST_KEY }

function newId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function stanceClass(stance) {
  if (!stance) return ''
  if (/strong_favorable|favorable|constructive|bullish/.test(stance)) return 'up'
  if (/cautious|unfavorable|bearish|avoid/.test(stance)) return 'down'
  return ''
}

function calcRewardR(entry, stop, target1) {
  const e = Number(entry)
  const s = Number(stop)
  const t = Number(target1)
  if (!e || !s || !t || e === s) return null
  return Math.round(((t - e) / Math.abs(e - s)) * 100) / 100
}

function distancePct(from, to) {
  if (!from || !to) return null
  return Math.round(((to - from) / from) * 1000) / 10
}

function SymbolSearchField({ value, onChange, onPick, searching, suggestions, placeholder, inputId }) {
  return (
    <div className="search-box swing-search-box">
      <input
        id={inputId}
        value={value}
        onChange={e => onChange(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter' && onPick) {
            e.preventDefault()
            onPick()
          }
        }}
        placeholder={placeholder}
        autoComplete="off"
        aria-autocomplete="list"
        aria-expanded={suggestions.length > 0}
      />
      {searching && <p className="search-hint">Searching…</p>}
      {suggestions.length > 0 && (
        <div className="suggestions" role="listbox">
          {suggestions.map(item => (
            <button
              key={`${item.symbol}-${item.exchange}`}
              type="button"
              role="option"
              onMouseDown={e => e.preventDefault()}
              onClick={() => onPick(item.symbol)}
            >
              <b>{item.symbol}</b>
              <span>{item.name} {item.exchange && `· ${item.exchange}`}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function SetupScoreCard({ setup, onCompare, onFullAnalyze }) {
  if (!setup) {
    return (
      <section className="panel swing-setup-card swing-empty-state">
        <p className="eyebrow">SWING SETUP</p>
        <h3>Scan a symbol to begin</h3>
        <p className="subtle">
          Search a name or ticker, then run <b>Scan setup</b> for 1W/1M blend score, levels, events, and a sized trade plan.
        </p>
      </section>
    )
  }

  const h = setup.horizons || {}
  const meta = setup.metadata || {}
  const events = setup.events?.items || []
  const earnings = setup.earnings
  const critical = setup.critical_signals || {}
  const distSignals = (critical.price_distortion?.signals || []).slice(0, 3)
  const rs = setup.relative_strength?.headline

  return (
    <section className="panel swing-setup-card">
      <div className="panel-head">
        <div>
          <p className="eyebrow">SWING SETUP</p>
          <h3>{setup.symbol} · grade {setup.grade}</h3>
        </div>
        <div className="swing-score-badge">
          <strong>{setup.setup_score ?? '—'}</strong>
          <span>score</span>
        </div>
      </div>
      <div className="swing-meta-badges">
        {meta.cached != null && (
          <span className={`ghost desk-tool-chip ${meta.cached ? 'is-cached' : 'is-fresh'}`}>
            {meta.cached ? 'Cached' : 'Fresh fetch'}
          </span>
        )}
        {meta.provider && <span className="ghost desk-tool-chip">Provider: {meta.provider}</span>}
        {setup.as_of && <span className="subtle">as of {setup.as_of}</span>}
      </div>
      <p className={`swing-action ${stanceClass(setup.stance)}`}>{setup.action?.replace(/_/g, ' ') || setup.stance}</p>
      <p>{setup.plain_english}</p>
      {setup.dossier_snippet?.plain_english && (
        <p className="subtle swing-dossier-snippet">{setup.dossier_snippet.plain_english}</p>
      )}
      <div className="swing-horizon-pills">
        <span className="ghost desk-tool-chip">1W {h['1w']?.grade || '—'} · {h['1w']?.score ?? '—'}</span>
        <span className="ghost desk-tool-chip">1M {h['1m']?.grade || '—'} · {h['1m']?.score ?? '—'}</span>
      </div>
      {rs?.plain && <p className="subtle swing-rs-line">RS: {rs.plain}</p>}
      {(setup.reasons || []).length > 0 && (
        <ul className="reason-list compact">
          {setup.reasons.map((r, i) => <li key={i}>{r}</li>)}
        </ul>
      )}
      <SwingMiniChart
        candles={setup.chart_candles}
        entry={setup.plan_hint?.entry}
        stop={setup.plan_hint?.stop}
        targets={setup.plan_hint?.targets || []}
      />
      {setup.levels && (
        <p className="subtle">
          Levels — pivot {setup.levels.pivot ?? '—'} · S1 {setup.levels.s1 ?? '—'} · R1 {setup.levels.r1 ?? '—'}
        </p>
      )}
      {earnings?.next_date && (
        <p className="swing-event-warn">
          Earnings: {earnings.next_date}{earnings.days_until != null ? ` (${earnings.days_until}d)` : ''}
        </p>
      )}
      {events.length > 0 && (
        <div className="swing-events-block">
          <p className="eyebrow">EVENTS & CATALYSTS</p>
          <ul className="reason-list compact">
            {events.slice(0, 5).map((ev, i) => (
              <li key={i}>
                <span className={`sig-pill sig-${ev.kind === 'risk' ? 'bearish' : 'neutral'}`}>{ev.label || ev.tag}</span>
                {' '}{ev.title}
              </li>
            ))}
          </ul>
        </div>
      )}
      {distSignals.length > 0 && (
        <div className="swing-events-block">
          <p className="eyebrow">CRITICAL SIGNALS</p>
          <ul className="reason-list compact">
            {distSignals.map((s, i) => <li key={i}>{s.plain_english || s.label}</li>)}
          </ul>
        </div>
      )}
      <div className="feature-controls swing-setup-links">
        {onCompare && <button type="button" className="ghost" onClick={() => onCompare(setup.symbol)}>Compare</button>}
        {onFullAnalyze && <button type="button" className="ghost" onClick={() => onFullAnalyze(setup.symbol)}>Full dossier</button>}
      </div>
      <p className="subtle">{setup.disclaimer}</p>
    </section>
  )
}

function TradePlanForm({
  setup, symbol, trades, onSaved, onError, bookRef, brokerPrefs, onBrokerOrder,
}) {
  const hint = setup?.plan_hint || {}
  const [entry, setEntry] = useState(hint.entry ?? '')
  const [stop, setStop] = useState(hint.stop ?? '')
  const [target1, setTarget1] = useState(hint.targets?.[0] ?? '')
  const [target2, setTarget2] = useState(hint.targets?.[1] ?? '')
  const [shares, setShares] = useState(hint.shares ?? '')
  const [trailingStop, setTrailingStop] = useState('')
  const [thesis, setThesis] = useState('')
  const [horizon, setHorizon] = useState('1w')
  const [capital, setCapital] = useState(hint.capital ?? 100000)
  const [riskPct, setRiskPct] = useState(hint.risk_pct ?? 1)
  const [rewardR, setRewardR] = useState(hint.reward_r ?? 2)
  const [atrStopMult, setAtrStopMult] = useState(hint.atr_stop_mult ?? 1.5)
  const [busy, setBusy] = useState(false)
  const [saveMsg, setSaveMsg] = useState('')
  const recalcTimer = useRef(null)

  useEffect(() => {
    const h = setup?.plan_hint || {}
    setEntry(h.entry ?? '')
    setStop(h.stop ?? '')
    setTarget1(h.targets?.[0] ?? '')
    setTarget2(h.targets?.[1] ?? '')
    setShares(h.shares ?? '')
    setCapital(h.capital ?? 100000)
    setRiskPct(h.risk_pct ?? 1)
    setRewardR(h.reward_r ?? 2)
    setAtrStopMult(h.atr_stop_mult ?? 1.5)
  }, [setup])

  const liveRr = calcRewardR(entry, stop, target1)

  const runRecalc = useCallback(async () => {
    if (!entry || Number(entry) <= 0) return
    try {
      const data = await apiPost('/api/swing/recalc', {
        entry: Number(entry),
        stop: stop ? Number(stop) : undefined,
        capital: Number(capital),
        risk_pct: Number(riskPct),
        atr: hint.atr,
        atr_stop_mult: Number(atrStopMult),
        reward_r: Number(rewardR),
      })
      if (data.shares != null) setShares(data.shares)
      if (data.stop && !stop) setStop(data.stop)
      if (data.targets?.length) {
        setTarget1(data.targets[0] ?? '')
        setTarget2(data.targets[1] ?? '')
      }
    } catch {
      /* sizing hint optional */
    }
  }, [entry, stop, capital, riskPct, atrStopMult, rewardR, hint.atr])

  useEffect(() => {
    if (recalcTimer.current) clearTimeout(recalcTimer.current)
    recalcTimer.current = setTimeout(runRecalc, 450)
    return () => { if (recalcTimer.current) clearTimeout(recalcTimer.current) }
  }, [capital, riskPct, stop, entry, atrStopMult, rewardR, runRecalc])

  function fillLevel(kind) {
    const lv = setup?.levels || {}
    const price = setup?.price
    if (kind === 'entry' && price) setEntry(price)
    if (kind === 'pivot' && lv.pivot) setEntry(lv.pivot)
    if (kind === 's1' && lv.s1) setStop(lv.s1)
    if (kind === 'r1' && lv.r1) setTarget1(lv.r1)
    if (kind === 'r2' && lv.r2) setTarget2(lv.r2)
  }

  async function savePlan(status = 'planned') {
    onError('')
    setSaveMsg('')
    const sym = symbol || setup?.symbol
    if (isDuplicatePlan(trades, sym, entry)) {
      onError(`Duplicate plan for ${sym} near ₹${entry} — edit existing or change entry.`)
      return
    }
    setBusy(true)
    try {
      const targets = [target1, target2].map(v => Number(v)).filter(v => v > 0)
      const plan = await apiPost('/api/swing/plan', {
        symbol: sym,
        entry: Number(entry),
        stop: Number(stop),
        targets,
        shares: Number(shares),
        thesis,
        horizon,
        capital: Number(capital),
        risk_pct: Number(riskPct),
        trailing_stop: trailingStop ? Number(trailingStop) : undefined,
        atr_stop_mult: Number(atrStopMult),
        reward_r: Number(rewardR),
      })
      const now = new Date().toISOString()
      const trade = {
        id: newId(),
        ...plan,
        status,
        setup_score: setup?.setup_score,
        created_at: now,
        activated_at: status === 'active' ? now : null,
        broker_order_id: null,
        partial_exits: [],
      }
      onSaved(trade)
      setSaveMsg(status === 'active' ? 'Plan saved & marked active.' : 'Plan saved to swing book.')
      bookRef?.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })

      if (status === 'active' && brokerPrefs.auto_buy_on_active && onBrokerOrder) {
        await onBrokerOrder(trade, 'buy')
      }
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (!setup) {
    return (
      <section className="panel swing-plan-form swing-empty-state">
        <p className="eyebrow">TRADE PLAN</p>
        <p className="subtle">Scan a setup first to pre-fill entry, stop, and ATR-sized shares.</p>
      </section>
    )
  }

  return (
    <section className="panel swing-plan-form">
      <div className="panel-head">
        <div><p className="eyebrow">TRADE PLAN</p><h3>Entry · stop · targets</h3></div>
        {liveRr != null && <span className="swing-rr-badge">{liveRr}R to T1</span>}
      </div>
      <div className="swing-level-fill feature-controls">
        <span className="subtle">Quick fill:</span>
        <button type="button" className="ghost" onClick={() => fillLevel('entry')}>Last</button>
        <button type="button" className="ghost" onClick={() => fillLevel('pivot')}>Pivot</button>
        <button type="button" className="ghost" onClick={() => fillLevel('s1')}>S1 stop</button>
        <button type="button" className="ghost" onClick={() => fillLevel('r1')}>R1 target</button>
        <button type="button" className="ghost" onClick={() => fillLevel('r2')}>R2 target</button>
      </div>
      <div className="desk-tool-form">
        <div className="desk-tool-form-row desk-tool-form-row--3">
          <label>
            Entry
            <input type="number" step="0.05" value={entry} onChange={e => setEntry(e.target.value)} />
          </label>
          <label>
            Stop
            <input type="number" step="0.05" value={stop} onChange={e => setStop(e.target.value)} />
          </label>
          <label>
            Shares
            <input type="number" min="1" value={shares} onChange={e => setShares(e.target.value)} />
          </label>
        </div>
        <div className="desk-tool-form-row">
          <label>
            Target 1
            <input type="number" step="0.05" value={target1} onChange={e => setTarget1(e.target.value)} />
          </label>
          <label>
            Target 2
            <input type="number" step="0.05" value={target2} onChange={e => setTarget2(e.target.value)} />
          </label>
          <label>
            Trailing stop
            <input type="number" step="0.05" value={trailingStop} onChange={e => setTrailingStop(e.target.value)} placeholder="Optional" />
          </label>
        </div>
        <div className="desk-tool-form-row desk-tool-form-row--3">
          <label>
            Horizon
            <select value={horizon} onChange={e => setHorizon(e.target.value)}>
              <option value="1w">1 week (max 5d hold)</option>
              <option value="1m">1 month (max 22d hold)</option>
            </select>
          </label>
          <label>
            Capital
            <input type="number" min="1000" value={capital} onChange={e => setCapital(e.target.value)} />
          </label>
          <label>
            Risk %
            <input type="number" min="0.1" max="5" step="0.1" value={riskPct} onChange={e => setRiskPct(e.target.value)} />
          </label>
        </div>
        <div className="desk-tool-form-row">
          <label>
            Reward R (sizing)
            <input type="number" min="0.5" max="5" step="0.1" value={rewardR} onChange={e => setRewardR(e.target.value)} />
          </label>
          <label>
            ATR stop mult
            <input type="number" min="0.5" max="4" step="0.1" value={atrStopMult} onChange={e => setAtrStopMult(e.target.value)} />
          </label>
        </div>
        <label>
          Thesis
          <textarea rows={3} value={thesis} onChange={e => setThesis(e.target.value)} placeholder="Why this swing — catalyst, level, trend…" />
        </label>
        {hint.plain && <p className="subtle">{hint.plain}</p>}
        {saveMsg && <p className="swing-save-msg">{saveMsg}</p>}
        <div className="desk-tool-form-actions">
          <button type="button" className="primary" disabled={busy} onClick={() => savePlan('planned')}>
            {busy ? 'Saving…' : 'Save plan'}
          </button>
          <button type="button" className="ghost" disabled={busy} onClick={() => savePlan('active')}>
            Mark active{brokerPrefs.auto_buy_on_active ? ' + buy stub' : ''}
          </button>
        </div>
      </div>
    </section>
  )
}

function ActiveTradesPanel({
  trades, setTrades, provider, onError, brokerPrefs, setBrokerPrefs,
  onBrokerOrder, onPortfolioBuy, onOpenJournal, onOpenBacktest, quotes, setQuotes,
}) {
  const [brokerStatus, setBrokerStatus] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [editId, setEditId] = useState(null)
  const [partialQty, setPartialQty] = useState({})

  useEffect(() => {
    apiGet('/api/broker/status').then(setBrokerStatus).catch(() => {})
  }, [])

  useEffect(() => {
    if (!brokerStatus) return
    const def = brokerStatus.default_broker
    const ad = brokerStatus.adapters?.[def]
    if (def && def !== 'stub' && ad?.live && brokerPrefs.broker === 'stub') {
      setBrokerPrefs(p => {
        const n = { ...p, broker: def }
        saveBrokerPrefs(n)
        return n
      })
    }
  }, [brokerStatus, brokerPrefs.broker, setBrokerPrefs])

  const brokerOptions = ['zerodha', 'groww', 'fyers'].map(id => {
    const ad = brokerStatus?.adapters?.[id] || {}
    const labels = { zerodha: 'Zerodha Kite', groww: 'Groww', fyers: 'FYERS' }
    let suffix = ''
    if (ad.live) suffix = ' · connected'
    else if (ad.configured) suffix = ' · configured'
    else suffix = ' · needs OAuth'
    return {
      id,
      label: `${labels[id] || id}${suffix}`,
      disabled: !ad.configured && !ad.live,
    }
  })

  const activeSymbols = trades.filter(t => t.status === 'active').map(t => t.symbol)
  useEffect(() => {
    if (!activeSymbols.length) return undefined
    let cancelled = false
    async function poll() {
      try {
        const data = await apiPost('/api/swing/pnl', { symbols: activeSymbols, provider })
        if (!cancelled && data.quotes) setQuotes(data.quotes)
      } catch { /* ignore */ }
    }
    poll()
    const id = setInterval(poll, 60000)
    return () => { cancelled = true; clearInterval(id) }
  }, [activeSymbols.join(','), provider, setQuotes])

  function patchTrade(id, patch) {
    setTrades(prev => prev.map(t => (t.id === id ? { ...t, ...patch, updated_at: new Date().toISOString() } : t)))
  }

  async function placeBrokerOrder(trade, side, qtyOverride) {
    onError('')
    setBusyId(trade.id)
    try {
      const qty = qtyOverride || trade.shares
      const order = await apiPost('/api/broker/order', {
        symbol: trade.symbol,
        side,
        quantity: qty,
        order_type: brokerPrefs.order_type || 'limit',
        limit_price: side === 'buy' ? trade.entry : (trade.targets?.[0] || trade.entry),
        stop_price: trade.stop,
        target_price: trade.targets?.[0],
        broker: brokerPrefs.broker || 'stub',
        product: brokerPrefs.product || 'cnc',
        trade_id: trade.id,
      })
      patchTrade(trade.id, {
        broker_order_id: order.order_id,
        broker_status: order.status,
        ...(side === 'buy' && !trade.activated_at ? { activated_at: new Date().toISOString(), status: 'active' } : {}),
      })
    } catch (err) {
      onError(err.message)
    } finally {
      setBusyId(null)
    }
  }

  function updateStatus(id, status) {
    const patch = { status }
    if (status === 'active') patch.activated_at = new Date().toISOString()
    if (status === 'closed') patch.closed_at = new Date().toISOString()
    patchTrade(id, patch)
  }

  function removeTrade(id) {
    setTrades(prev => prev.filter(t => t.id !== id))
  }

  async function saveEdit(trade, form) {
    try {
      const plan = await apiPost('/api/swing/plan', {
        symbol: trade.symbol,
        entry: Number(form.entry),
        stop: Number(form.stop),
        targets: [form.target1, form.target2].map(Number).filter(v => v > 0),
        shares: Number(form.shares),
        thesis: form.thesis,
        horizon: form.horizon,
        capital: trade.capital || 100000,
        risk_pct: trade.risk_pct || 1,
        trailing_stop: form.trailingStop ? Number(form.trailingStop) : trade.trailing_stop,
      })
      patchTrade(trade.id, plan)
      setEditId(null)
    } catch (err) {
      onError(err.message)
    }
  }

  function partialExit(trade) {
    const qty = Number(partialQty[trade.id] || 0)
    if (qty <= 0 || qty >= trade.shares) {
      onError('Enter partial qty less than total shares.')
      return
    }
    const exits = [...(trade.partial_exits || []), { qty, at: new Date().toISOString() }]
    patchTrade(trade.id, { shares: trade.shares - qty, partial_exits: exits })
    placeBrokerOrder({ ...trade, shares: qty }, 'sell', qty)
  }

  const open = trades.filter(t => t.status !== 'closed')
  const closed = trades.filter(t => t.status === 'closed')
  const activeCount = trades.filter(t => t.status === 'active').length
  const plannedCount = trades.filter(t => t.status === 'planned').length

  return (
    <section className="panel swing-trades-panel" ref={undefined}>
      <div className="panel-head">
        <div><p className="eyebrow">SWING BOOK</p><h3>Plans & active holds</h3></div>
        <span className="subtle">{activeCount} active · {plannedCount} planned · {trades.length} total</span>
      </div>
      <div className="swing-broker-controls desk-tool-form-row">
        <label>
          Broker
          <select
            value={brokerPrefs.broker}
            onChange={e => setBrokerPrefs(p => { const n = { ...p, broker: e.target.value }; saveBrokerPrefs(n); return n })}
          >
            <option value="stub">Stub (local queue)</option>
            {brokerOptions.map(b => (
              <option key={b.id} value={b.id} disabled={b.disabled}>{b.label}</option>
            ))}
          </select>
        </label>
        <label>
          Product
          <select
            value={brokerPrefs.product}
            onChange={e => setBrokerPrefs(p => { const n = { ...p, product: e.target.value }; saveBrokerPrefs(n); return n })}
          >
            <option value="cnc">CNC / delivery</option>
            <option value="mis">MIS / intraday</option>
          </select>
        </label>
        <label>
          Order type
          <select
            value={brokerPrefs.order_type}
            onChange={e => setBrokerPrefs(p => { const n = { ...p, order_type: e.target.value }; saveBrokerPrefs(n); return n })}
          >
            <option value="limit">Limit</option>
            <option value="market">Market</option>
            <option value="sl">SL</option>
            <option value="sl-m">SL-M</option>
          </select>
        </label>
        <label className="refresh-toggle">
          <input
            type="checkbox"
            checked={brokerPrefs.auto_buy_on_active}
            onChange={e => setBrokerPrefs(p => {
              const n = { ...p, auto_buy_on_active: e.target.checked }
              saveBrokerPrefs(n)
              return n
            })}
          />
          Auto buy on active
        </label>
      </div>
      {brokerStatus && (
        <p className="subtle swing-broker-note">
          Broker: <b>{brokerStatus.default_broker || brokerStatus.mode}</b>
          {brokerStatus.gateway?.enabled && (
            <> · via gateway {brokerStatus.gateway.url}</>
          )}
          {brokerStatus.gateway?.static_ip && (
            <> · static IP {brokerStatus.gateway.static_ip}</>
          )}
          {' '}— {brokerStatus.message || brokerStatus.adapters?.[brokerPrefs.broker]?.message}
        </p>
      )}
      <div className="feature-controls swing-book-export">
        <button type="button" className="ghost" onClick={() => exportSwingBook(trades)}>Export JSON</button>
        <button type="button" className="ghost" onClick={() => exportSwingBookCsv(trades)}>Export CSV</button>
      </div>
      {open.length === 0 && <p className="subtle">No open swing plans. Scan a setup and save a trade plan.</p>}
      <div className="swing-trades-list">
        {open.map(trade => {
          const q = quotes[trade.symbol]
          const last = q?.price
          const pnl = last != null ? (last - trade.entry) * trade.shares : null
          const pnlPct = last != null ? distancePct(trade.entry, last) : null
          const distStop = last != null ? distancePct(last, trade.stop) : null
          const distTgt = last != null && trade.targets?.[0] ? distancePct(last, trade.targets[0]) : null
          const held = trade.status === 'active' ? daysHeld(trade) : null
          const maxHold = trade.max_hold_days || (trade.horizon === '1m' ? 22 : 5)
          const holdWarn = held != null && held >= maxHold

          return (
            <article key={trade.id} className={`swing-trade-card status-${trade.status}`}>
              <div className="swing-trade-head">
                <strong>{trade.symbol}</strong>
                <span className={`sig-pill sig-${trade.status === 'active' ? 'bullish' : 'neutral'}`}>{trade.status}</span>
                <span className="subtle">{trade.horizon?.toUpperCase()}</span>
                {trade.reward_r != null && <span className="swing-rr-badge">{number.format(trade.reward_r)}R</span>}
              </div>
              <p>
                Entry {money.format(trade.entry)} · Stop {money.format(trade.stop)} · {trade.shares} sh
              </p>
              {(trade.targets || []).length > 0 && (
                <p className="subtle">Targets: {trade.targets.map(t => money.format(t)).join(' · ')}</p>
              )}
              {trade.trailing_stop && <p className="subtle">Trail stop: {money.format(trade.trailing_stop)}</p>}
              {trade.status === 'active' && last != null && (
                <p className={`swing-pnl-line ${(pnl ?? 0) >= 0 ? 'up' : 'down'}`}>
                  Live {money.format(last)} · P&L {money.format(pnl)} ({pnlPct >= 0 ? '+' : ''}{pnlPct}%)
                  · Stop {distStop}% away · T1 {distTgt}% away
                </p>
              )}
              {held != null && (
                <p className={`subtle ${holdWarn ? 'swing-hold-warn' : ''}`}>
                  Days held {held}/{maxHold}{holdWarn ? ' — review max hold' : ''}
                </p>
              )}
              {trade.thesis && <p className="subtle">{trade.thesis}</p>}
              {trade.broker_order_id && <p className="subtle">Order {trade.broker_order_id}</p>}
              {(trade.partial_exits || []).length > 0 && (
                <p className="subtle">Partial exits: {trade.partial_exits.map(p => `${p.qty}@${p.at?.slice(0, 10)}`).join(', ')}</p>
              )}

              {editId === trade.id ? (
                <EditTradeForm trade={trade} onSave={f => saveEdit(trade, f)} onCancel={() => setEditId(null)} />
              ) : (
                <div className="feature-controls">
                  {trade.status === 'planned' && (
                    <>
                      <button type="button" className="primary" disabled={busyId === trade.id} onClick={() => placeBrokerOrder(trade, 'buy')}>
                        {busyId === trade.id ? 'Sending…' : 'Buy (stub)'}
                      </button>
                      <button type="button" className="ghost" onClick={() => updateStatus(trade.id, 'active')}>Activate</button>
                    </>
                  )}
                  {trade.status === 'active' && (
                    <>
                      <button type="button" className="ghost" disabled={busyId === trade.id} onClick={() => placeBrokerOrder(trade, 'sell')}>
                        {busyId === trade.id ? 'Sending…' : 'Exit (stub)'}
                      </button>
                      <input
                        type="number"
                        min="1"
                        max={trade.shares - 1}
                        placeholder="Partial qty"
                        value={partialQty[trade.id] || ''}
                        onChange={e => setPartialQty(s => ({ ...s, [trade.id]: e.target.value }))}
                        className="swing-partial-input"
                      />
                      <button type="button" className="ghost" onClick={() => partialExit(trade)}>Partial</button>
                      <button type="button" className="ghost" onClick={() => updateStatus(trade.id, 'closed')}>Close</button>
                    </>
                  )}
                  <button type="button" className="ghost" onClick={() => setEditId(trade.id)}>Edit</button>
                  {onPortfolioBuy && (
                    <button type="button" className="ghost" onClick={() => onPortfolioBuy(trade)}>Paper buy</button>
                  )}
                  {onOpenJournal && (
                    <button type="button" className="ghost" onClick={() => { appendJournalEntry(trade); onOpenJournal() }}>Journal</button>
                  )}
                  {onOpenBacktest && (
                    <button type="button" className="ghost" onClick={onOpenBacktest}>Backtest</button>
                  )}
                  <button type="button" className="ghost" onClick={() => removeTrade(trade.id)}>Remove</button>
                </div>
              )}
            </article>
          )
        })}
      </div>
      {closed.length > 0 && (
        <>
          <p className="eyebrow" style={{ marginTop: 16 }}>Closed ({closed.length})</p>
          <div className="swing-trades-list">
            {closed.slice(0, 12).map(t => (
              <article key={t.id} className="swing-trade-card status-closed">
                <div className="swing-trade-head">
                  <strong>{t.symbol}</strong>
                  <span className="subtle">{t.horizon?.toUpperCase()}</span>
                </div>
                <p>
                  {t.shares} sh · entry {money.format(t.entry)} · stop {money.format(t.stop)}
                  {t.closed_at && <> · closed {t.closed_at.slice(0, 10)}</>}
                </p>
                {t.thesis && <p className="subtle">{t.thesis}</p>}
                {t.reward_r != null && <p className="subtle">{number.format(t.reward_r)}R plan</p>}
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  )
}

function EditTradeForm({ trade, onSave, onCancel }) {
  const [entry, setEntry] = useState(trade.entry)
  const [stop, setStop] = useState(trade.stop)
  const [shares, setShares] = useState(trade.shares)
  const [target1, setTarget1] = useState(trade.targets?.[0] ?? '')
  const [target2, setTarget2] = useState(trade.targets?.[1] ?? '')
  const [thesis, setThesis] = useState(trade.thesis || '')
  const [horizon, setHorizon] = useState(trade.horizon || '1w')
  const [trailingStop, setTrailingStop] = useState(trade.trailing_stop ?? '')

  return (
    <div className="desk-tool-form swing-edit-form">
      <div className="desk-tool-form-row desk-tool-form-row--3">
        <label>Entry<input type="number" value={entry} onChange={e => setEntry(e.target.value)} /></label>
        <label>Stop<input type="number" value={stop} onChange={e => setStop(e.target.value)} /></label>
        <label>Shares<input type="number" value={shares} onChange={e => setShares(e.target.value)} /></label>
      </div>
      <div className="desk-tool-form-row">
        <label>T1<input type="number" value={target1} onChange={e => setTarget1(e.target.value)} /></label>
        <label>T2<input type="number" value={target2} onChange={e => setTarget2(e.target.value)} /></label>
        <label>Trail<input type="number" value={trailingStop} onChange={e => setTrailingStop(e.target.value)} /></label>
      </div>
      <label>Thesis<textarea rows={2} value={thesis} onChange={e => setThesis(e.target.value)} /></label>
      <div className="feature-controls">
        <button type="button" className="primary" onClick={() => onSave({ entry, stop, shares, target1, target2, thesis, horizon, trailingStop })}>Save</button>
        <button type="button" className="ghost" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  )
}

function SwingAlertsPanel({ alerts, setAlerts, watchlist, setup, onError }) {
  const [symbol, setSymbol] = useState('')
  const [above, setAbove] = useState('')
  const [below, setBelow] = useState('')

  function addAlert() {
    const sym = (symbol || setup?.symbol || '').trim().toUpperCase()
    if (!sym) {
      onError('Enter a symbol for the alert.')
      return
    }
    if (!above && !below) {
      onError('Set price above or below threshold.')
      return
    }
    const row = {
      id: newId(),
      symbol: sym,
      above: above ? Number(above) : null,
      below: below ? Number(below) : null,
      created_at: new Date().toISOString(),
    }
    const next = [row, ...alerts]
    setAlerts(next)
    saveSwingAlerts(next)
    setSymbol('')
    setAbove('')
    setBelow('')
  }

  async function checkAlerts(quotes) {
    const notify = loadStore('stockAddaNotify', {})
    const fired = []
    for (const a of alerts) {
      const price = quotes[a.symbol]?.price ?? setup?.price
      if (price == null) continue
      if (a.above != null && price >= a.above) fired.push(`${a.symbol} ≥ ${a.above} (now ${price})`)
      if (a.below != null && price <= a.below) fired.push(`${a.symbol} ≤ ${a.below} (now ${price})`)
    }
    if (fired.length && notify.webhook_url) {
      try {
        await apiPost('/api/desk/notify', { message: `Swing alerts:\n${fired.join('\n')}`, webhook_url: notify.webhook_url })
      } catch { /* optional */ }
    }
    return fired
  }

  return (
    <section className="panel swing-alerts-panel">
      <div className="panel-head">
        <div><p className="eyebrow">PRICE ALERTS</p><h3>Persistent levels</h3></div>
        <span className="subtle">{alerts.length}</span>
      </div>
      <div className="desk-tool-form-row">
        <label>
          Symbol
          <input value={symbol} onChange={e => setSymbol(e.target.value)} placeholder={setup?.symbol || 'RELIANCE.NSE'} />
        </label>
        <label>
          Above
          <input type="number" value={above} onChange={e => setAbove(e.target.value)} />
        </label>
        <label>
          Below
          <input type="number" value={below} onChange={e => setBelow(e.target.value)} />
        </label>
        <button type="button" className="primary" onClick={addAlert}>Add</button>
      </div>
      <ul className="reason-list compact">
        {alerts.length === 0 && <li className="subtle">No alerts — add entry/stop triggers. Wire Notify desk for webhooks.</li>}
        {alerts.map(a => (
          <li key={a.id}>
            <b>{a.symbol}</b>
            {a.above != null && <> ≥ {a.above}</>}
            {a.below != null && <> ≤ {a.below}</>}
            <button
              type="button"
              className="ghost"
              onClick={() => {
                const next = alerts.filter(x => x.id !== a.id)
                setAlerts(next)
                saveSwingAlerts(next)
              }}
            >
              Remove
            </button>
          </li>
        ))}
      </ul>
      {/* expose checkAlerts via ref pattern — called from parent scan */}
      <SwingAlertsChecker alerts={alerts} setup={setup} watchlist={watchlist} checkAlerts={checkAlerts} />
    </section>
  )
}

function SwingAlertsChecker({ alerts, setup, watchlist, checkAlerts }) {
  const [fired, setFired] = useState([])

  useEffect(() => {
    if (!alerts.length) return undefined
    const syms = [...new Set([...alerts.map(a => a.symbol), ...(watchlist || [])])]
    let cancelled = false
    async function run() {
      try {
        const data = await apiPost('/api/swing/pnl', { symbols: syms, provider: 'auto' })
        if (cancelled) return
        if (setup?.symbol && setup?.price) {
          data.quotes = { ...data.quotes, [setup.symbol]: { price: setup.price } }
        }
        const hits = await checkAlerts(data.quotes || {})
        if (hits.length) setFired(hits)
      } catch { /* ignore */ }
    }
    run()
    const id = setInterval(run, 120000)
    return () => { cancelled = true; clearInterval(id) }
  }, [alerts.length, setup?.symbol, watchlist?.length])

  if (!fired.length) return null
  return (
    <div className="swing-alert-fired">
      <p className="eyebrow">ALERTS FIRED</p>
      <ul className="reason-list compact">{fired.map((m, i) => <li key={i}>{m}</li>)}</ul>
    </div>
  )
}

function SwingWatchlist({ list, setList, onScan, onSelect, onError }) {
  const watchSearch = useSymbolSearch('')

  async function add() {
    onError('')
    const sym = await watchSearch.resolveSymbol()
    if (!sym) {
      onError('Pick a symbol from suggestions (e.g. JIOFIN.NSE).')
      return
    }
    if (list.includes(sym)) return
    setList(prev => [...prev, sym])
    watchSearch.setQuery('')
    watchSearch.clearSuggestions()
  }

  return (
    <section className="panel swing-watch-panel">
      <div className="panel-head">
        <div><p className="eyebrow">SWING WATCH</p><h3>Candidate list</h3></div>
        <span className="subtle">{list.length}</span>
      </div>
      <div className="feature-controls swing-watch-add">
        <SymbolSearchField
          value={watchSearch.query}
          onChange={watchSearch.onQueryChange}
          onPick={sym => {
            if (sym) {
              if (!list.includes(sym)) setList(prev => [...prev, sym])
              watchSearch.setQuery('')
              watchSearch.clearSuggestions()
            } else {
              add()
            }
          }}
          searching={watchSearch.searching}
          suggestions={watchSearch.suggestions}
          placeholder="Search e.g. Jio or TCS"
        />
        <button type="button" className="primary" onClick={add}>Add</button>
        {list.length > 0 && (
          <button type="button" className="ghost" onClick={onScan}>Scan alerts</button>
        )}
      </div>
      <ul className="reason-list compact">
        {list.length === 0 && <li className="subtle">Add symbols from screener or manual entry.</li>}
        {list.map(sym => (
          <li key={sym}>
            <b>{sym}</b>
            <button type="button" className="ghost" onClick={() => onSelect(sym)}>Setup</button>
            <button type="button" className="ghost" onClick={() => setList(prev => prev.filter(s => s !== sym))}>Remove</button>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function SwingDeskPage({
  symbol,
  setSymbol,
  provider: providerProp,
  screenProviders,
  onError,
  onAnalyze,
  go,
  setHorizon,
  seedAnalysis,
  onPortfolioBuy,
  onOpenJournal,
  onOpenBacktest,
  onCompare,
}) {
  const [sym, setSym] = useState(symbol || 'RELIANCE.NSE')
  const [localProvider, setLocalProvider] = useState(providerProp || 'auto')
  const provider = localProvider || providerProp || 'auto'
  const symbolSearch = useSymbolSearch(symbol || 'RELIANCE.NSE')
  const [forceRefresh, setForceRefresh] = useState(false)
  const [busy, setBusy] = useState(false)
  const [setup, setSetup] = useState(null)
  const [trades, setTrades] = useState(() => loadStore(SWING_TRADES_KEY, []))
  const [watchlist, setWatchlist] = useState(() => loadStore(SWING_WATCHLIST_KEY, []))
  const [scanResult, setScanResult] = useState(null)
  const [alerts, setAlerts] = useState(() => loadSwingAlerts())
  const [quotes, setQuotes] = useState({})
  const [brokerPrefs, setBrokerPrefs] = useState(() => loadBrokerPrefs())
  const bookRef = useRef(null)
  const autoRefreshRef = useRef(null)

  useEffect(() => { saveStore(SWING_TRADES_KEY, trades) }, [trades])
  useEffect(() => { saveStore(SWING_WATCHLIST_KEY, watchlist) }, [watchlist])
  useEffect(() => { if (symbol) { setSym(symbol); symbolSearch.setQuery(symbol) } }, [symbol])
  useEffect(() => { if (providerProp) setLocalProvider(providerProp) }, [providerProp])

  useEffect(() => {
    if (!seedAnalysis?.ratings?.horizons) return
    const h1w = seedAnalysis.ratings.horizons['1w']
    const h1m = seedAnalysis.ratings.horizons['1m']
    if (!h1w && !h1m) return
    setSetup(prev => prev || {
      symbol: seedAnalysis.symbol,
      setup_score: Math.round(((h1w?.score || 50) + (h1m?.score || 50)) / 2 * 10) / 10,
      horizons: { '1w': h1w, '1m': h1m },
      plan_hint: seedAnalysis.position_size_hint,
      levels: seedAnalysis.technicals?.levels,
      as_of: seedAnalysis.technicals?.as_of,
      price: seedAnalysis.technicals?.price,
      plain_english: seedAnalysis.dossier?.conviction?.plain_english || 'Loaded from Analyze tab — run Scan setup for full swing score.',
      disclaimer: 'Seed from Analyze — click Scan setup for full 1W/1M blend.',
    })
  }, [seedAnalysis])

  const scanSetup = useCallback(async (selected) => {
    onError('')
    let target = selected
    if (!target) {
      target = await symbolSearch.resolveSymbol()
    }
    if (!target) {
      onError('Pick a symbol from suggestions (e.g. type Jio and select JIOFIN.NSE).')
      return
    }
    target = target.trim().toUpperCase()
    setBusy(true)
    setScanResult(null)
    symbolSearch.setQuery(target)
    setSym(target)
    try {
      const data = await apiPost('/api/swing/setup', {
        symbol: target,
        provider,
        force_refresh: forceRefresh,
        with_dossier: true,
        capital: 100000,
        risk_pct: 1,
      })
      setSetup(data)
      if (setSymbol) setSymbol(target)
      symbolSearch.clearSuggestions()
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }, [provider, forceRefresh, onError, setSymbol, symbolSearch])

  useEffect(() => {
    const active = trades.some(t => t.status === 'active')
    if (!active) return undefined
    autoRefreshRef.current = setInterval(() => {
      if (sym) scanSetup(sym)
    }, 300000)
    return () => { if (autoRefreshRef.current) clearInterval(autoRefreshRef.current) }
  }, [trades.filter(t => t.status === 'active').length, sym, scanSetup])

  async function scanWatchlist() {
    if (!watchlist.length) return
    onError('')
    try {
      const data = await apiPost('/api/desk/watch-scan', {
        symbols: watchlist.slice(0, 12),
        provider,
        rules: { rsi_high: 70, rsi_low: 30 },
      })
      setScanResult(data)
    } catch (err) {
      onError(err.message)
    }
  }

  function onPlanSaved(trade) {
    setTrades(prev => [trade, ...prev])
  }

  async function handleBrokerOrder(trade, side) {
    onError('')
    try {
      const order = await apiPost('/api/broker/order', {
        symbol: trade.symbol,
        side,
        quantity: trade.shares,
        order_type: brokerPrefs.order_type || 'limit',
        limit_price: side === 'buy' ? trade.entry : (trade.targets?.[0] || trade.entry),
        stop_price: trade.stop,
        target_price: trade.targets?.[0],
        broker: brokerPrefs.broker || 'stub',
        product: brokerPrefs.product || 'cnc',
        trade_id: trade.id,
      })
      setTrades(prev => prev.map(t => (
        t.id === trade.id
          ? {
            ...t,
            broker_order_id: order.order_id,
            broker_status: order.status,
            status: side === 'buy' ? 'active' : t.status,
            activated_at: side === 'buy' ? (t.activated_at || new Date().toISOString()) : t.activated_at,
          }
          : t
      )))
    } catch (err) {
      onError(err.message)
    }
  }

  function openScreener(horizonKey) {
    if (setHorizon) setHorizon(horizonKey)
    if (go) go('multi')
  }

  const providerOptions = screenProviders?.providers || [
    { id: 'auto', label: 'Auto' },
    { id: 'yfinance', label: 'Yahoo' },
    { id: 'nse', label: 'NSE' },
  ]
  const liveBroker = (screenProviders?.brokers || []).find(b => b.live)
  const liveQuote = screenProviders?.live_quote

  return (
    <div className="swing-desk">
      <section className="panel swing-hero">
        <div className="panel-head">
          <div>
            <p className="eyebrow">SWING DESK</p>
            <h2>Multi-day setups · 1W / 1M · broker-ready plans</h2>
          </div>
        </div>
        <p className="subtle">
          Scan horizon-aligned setups, build ATR-sized trade plans, track live P&amp;L, and route orders through your broker.
          {liveBroker
            ? ` Live LTP via ${liveBroker.label}; charts still use Yahoo/NSE daily bars.`
            : ' Connect Kite/Groww/FYERS in Accounts — until then Yahoo feeds live pulse and paper fills.'}
        </p>
        <div className="swing-hero-controls">
          <label className="swing-search-label">
            Symbol
            <SymbolSearchField
              inputId="swing-symbol-search"
              value={symbolSearch.query}
              onChange={symbolSearch.onQueryChange}
              onPick={sym => (sym ? scanSetup(sym) : scanSetup())}
              searching={symbolSearch.searching}
              suggestions={symbolSearch.suggestions}
              placeholder="Search name or code, e.g. Jio or RELIANCE.NSE"
            />
          </label>
          <div className="swing-hero-actions feature-controls">
            <label>
              Data
              <select value={localProvider} onChange={e => setLocalProvider(e.target.value)}>
                {providerOptions.map(p => (
                  <option key={p.id} value={p.id}>{p.label}</option>
                ))}
              </select>
            </label>
            {liveQuote && liveQuote.transport && liveQuote.transport !== 'none' && (
              <span className="subtle" style={{ alignSelf: 'center' }}>
                Live: {liveQuote.source || 'broker'} · {liveQuote.transport}
                {liveQuote.connected === false ? ' (disconnected)' : ''}
              </span>
            )}
            <label className="refresh-toggle">
              <input type="checkbox" checked={forceRefresh} onChange={e => setForceRefresh(e.target.checked)} />
              Refresh
            </label>
            <button type="button" className="primary" disabled={busy} onClick={() => scanSetup()}>
              {busy ? 'Scanning…' : 'Scan setup'}
            </button>
            <button type="button" className="ghost" onClick={() => openScreener('1w')}>1W screener</button>
            <button type="button" className="ghost" onClick={() => openScreener('1m')}>1M screener</button>
            {onAnalyze && (
              <button
                type="button"
                className="ghost"
                onClick={async () => {
                  const target = await symbolSearch.resolveSymbol()
                  if (target) onAnalyze(target)
                  else onError('Pick a symbol from suggestions first.')
                }}
              >
                Full analyze
              </button>
            )}
          </div>
        </div>
      </section>

      <PlatformLimitationsPanel compact />

      <div className="swing-desk-grid">
        <div className="swing-desk-main">
          <SetupScoreCard
            setup={setup}
            onCompare={onCompare ? () => onCompare(sym) : null}
            onFullAnalyze={onAnalyze ? () => onAnalyze(sym) : null}
          />
          <TradePlanForm
            setup={setup}
            symbol={sym}
            trades={trades}
            onSaved={onPlanSaved}
            onError={onError}
            bookRef={bookRef}
            brokerPrefs={brokerPrefs}
            onBrokerOrder={handleBrokerOrder}
          />
        </div>
        <div className="swing-desk-side">
          <SwingWatchlist
            list={watchlist}
            setList={setWatchlist}
            onScan={scanWatchlist}
            onSelect={s => scanSetup(s)}
            onError={onError}
          />
          <SwingAlertsPanel alerts={alerts} setAlerts={setAlerts} watchlist={watchlist} setup={setup} onError={onError} />
          <div ref={bookRef}>
            <ActiveTradesPanel
              trades={trades}
              setTrades={setTrades}
              provider={provider}
              onError={onError}
              brokerPrefs={brokerPrefs}
              setBrokerPrefs={setBrokerPrefs}
              onBrokerOrder={handleBrokerOrder}
              onPortfolioBuy={onPortfolioBuy}
              onOpenJournal={onOpenJournal}
              onOpenBacktest={onOpenBacktest}
              quotes={quotes}
              setQuotes={setQuotes}
            />
          </div>
          {scanResult?.alerts?.length > 0 && (
            <section className="panel">
              <p className="eyebrow">WATCH SCAN</p>
              <ul className="reason-list compact">
                {scanResult.alerts.map((a, i) => (
                  <li key={i}><b>{a.symbol}</b> — {a.message}</li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}

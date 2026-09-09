import { useEffect, useMemo, useState } from 'react'
import { apiPost } from './lib/apiClient'
import { loadStore, saveStore } from './lib/storage'

const number = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 })
const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })

const JOURNAL_KEY = 'scanBhavJournal'
const WATCHLIST_KEY = 'scanBhavWatchlist'

const ASK_PRESETS = [
  'Explain RSI for beginners',
  'Is this stock too risky for a first investor?',
  'What should I monitor next?',
]

const GLOSSARY = [
  { title: 'Trend', body: 'Direction of price over time. Rising highs and lows suggest an uptrend; falling highs and lows suggest a downtrend. Trends can reverse — use stops and position size.' },
  { title: 'RSI', body: 'Relative Strength Index measures momentum on a 0–100 scale. Above 70 is often called overbought; below 30 oversold. It flags stretch, not guaranteed reversals.' },
  { title: 'Diversification', body: 'Spreading capital across sectors and asset types so one bad outcome does not dominate your portfolio. Correlated names still move together.' },
  { title: 'SIP vs lump sum', body: 'SIP invests fixed amounts on a schedule, smoothing entry timing. Lump sum invests once — higher timing risk but full market exposure immediately.' },
  { title: 'Risk %', body: 'The share of capital you are willing to lose on one trade if your stop hits. Position size = risk rupees ÷ stop distance per share.' },
]

function deriveAction(analysis) {
  const raw = (
    analysis?.ratings?.composite_stance
    || analysis?.dossier?.conviction?.band
    || 'wait'
  ).toString().toLowerCase()
  if (/bullish|favorable|buy|strong_buy/.test(raw)) return 'buy'
  if (/cautious|bearish|avoid|sell|weak/.test(raw)) return 'avoid'
  return 'wait'
}

function decodedSummary(dossier) {
  const decoded = dossier?.decoded
  if (!decoded) return ''
  if (decoded.summary) return decoded.summary
  const facts = decoded.facts || []
  if (facts.length) {
    return facts.slice(0, 2).map(f => f.body || f.title).filter(Boolean).join(' ')
  }
  return decoded.headline || ''
}

function mondayKey(dateStr) {
  const d = new Date(dateStr)
  if (Number.isNaN(d.getTime())) return dateStr
  const day = d.getDay()
  const diff = day === 0 ? -6 : 1 - day
  const mon = new Date(d)
  mon.setDate(d.getDate() + diff)
  return mon.toISOString().slice(0, 10)
}

function bucketCandles(group) {
  if (!group.length) return null
  const first = group[0]
  const last = group[group.length - 1]
  const highs = group.map(c => Number(c.high ?? c.close ?? 0))
  const lows = group.map(c => Number(c.low ?? c.close ?? 0))
  return {
    ...last,
    date: last.date,
    open: first.open ?? first.close,
    high: Math.max(...highs),
    low: Math.min(...lows),
    close: last.close,
    volume: group.reduce((s, c) => s + Number(c.volume || 0), 0),
    sma_20: last.sma_20,
    sma_50: last.sma_50,
    vwap: last.vwap,
    rsi_14: last.rsi_14,
    atr_14: last.atr_14,
    atr_pct: last.atr_pct,
    atr_upper: last.atr_upper,
    atr_lower: last.atr_lower,
    macd: last.macd,
    macd_signal: last.macd_signal,
    macd_hist: last.macd_hist,
    ema_21: last.ema_21,
    bb_upper: last.bb_upper,
    bb_lower: last.bb_lower,
    pivot_line: last.pivot_line,
    r1_line: last.r1_line,
    s1_line: last.s1_line,
  }
}

export function aggregateTimeframe(candles, tf) {
  if (!candles?.length) return []
  if (!tf || tf === '1D') return candles

  if (tf === '1W') {
    const byWeek = new Map()
    for (const c of candles) {
      const key = mondayKey(c.date)
      if (!byWeek.has(key)) byWeek.set(key, [])
      byWeek.get(key).push(c)
    }
    const weeks = [...byWeek.values()]
    if (weeks.length <= 1 && candles.length >= 5) {
      const chunks = []
      for (let i = 0; i < candles.length; i += 5) {
        const chunk = candles.slice(i, i + 5)
        if (chunk.length) chunks.push(bucketCandles(chunk))
      }
      return chunks
    }
    return weeks.map(bucketCandles).filter(Boolean)
  }

  if (tf === '1M') {
    const byMonth = new Map()
    for (const c of candles) {
      const key = (c.date || '').slice(0, 7)
      if (!byMonth.has(key)) byMonth.set(key, [])
      byMonth.get(key).push(c)
    }
    return [...byMonth.values()].map(bucketCandles).filter(Boolean)
  }

  return candles
}

export function exportBrief(analysis, genaiResult) {
  if (!analysis) return
  const action = deriveAction(analysis)
  const dossier = analysis.dossier || {}
  const radar = dossier.signal_radar || {}
  const conviction = dossier.conviction || {}
  const tech = analysis.technicals || {}
  const ratings = analysis.ratings || {}
  const insight = genaiResult?.insight || genaiResult?.synthesis || null
  const lines = [
    `# ${analysis.symbol} — Research brief`,
  ]
  if (analysis.quote?.company?.name) lines.push(`**${analysis.quote.company.name}**`)
  lines.push('', '## Verdict', `- Action: **${action}**`, `- ${conviction.plain_english || decodedSummary(dossier) || 'No conviction note.'}`)
  if (analysis.relative_strength?.headline?.plain) {
    lines.push(`- Relative strength: ${analysis.relative_strength.headline.plain}`)
  }
  lines.push('', '## Key metrics')
  lines.push(`- Price: ${tech.price != null ? number.format(tech.price) : '—'}`)
  lines.push(`- Composite score: ${ratings.composite_score ?? '—'} (${ratings.composite_grade || '—'})`)
  lines.push(`- RSI 14: ${tech.momentum?.rsi_14 ?? '—'}`)
  lines.push(`- ATR 14: ${tech.volatility?.atr_14 ?? '—'}`)
  if (analysis.position_size_hint?.plain) {
    lines.push(`- Position hint: ${analysis.position_size_hint.plain}`)
  }
  lines.push('', '## Dossier flags')
  const greens = radar.green_flags || []
  const reds = radar.red_flags || []
  if (greens.length) {
    lines.push('### Green flags')
    greens.forEach(g => lines.push(`- ${g}`))
  }
  if (reds.length) {
    lines.push('### Red flags')
    reds.forEach(r => lines.push(`- ${r}`))
  }
  if (!greens.length && !reds.length) lines.push('No dossier flags recorded.')
  if (insight?.executive_summary || insight?.summary) {
    lines.push('', '## GenAI executive summary')
    lines.push(insight.executive_summary || insight.summary)
  }
  lines.push('', '---', 'Educational research only — not investment advice.')
  const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${analysis.symbol.replace(/[^a-zA-Z0-9._-]/g, '_')}_brief.md`
  a.click()
  URL.revokeObjectURL(url)
}

export function VerdictStrip({ analysis, beginnerMode }) {
  if (!analysis) return null
  const action = deriveAction(analysis)
  const dossier = analysis.dossier || {}
  const radar = dossier.signal_radar || {}
  const copy = dossier.conviction?.plain_english || decodedSummary(dossier)
  const redFlag = (radar.red_flags || [])[0]
  const rsPlain = analysis.relative_strength?.headline?.plain

  const actionLabel = action === 'buy' ? 'Buy' : action === 'avoid' ? 'Avoid' : 'Wait'

  return (
    <section className="panel verdict-strip">
      <span className={`verdict-action ${action}`}>{actionLabel}</span>
      <div className="verdict-copy">
        {copy && <p>{beginnerMode ? copy.split('.').slice(0, 2).join('.').trim() : copy}</p>}
        {redFlag && (
          <p className="subtle">What could go wrong: {typeof redFlag === 'string' ? redFlag : redFlag.text || redFlag.title}</p>
        )}
        {rsPlain && <p className="subtle">{rsPlain}</p>}
      </div>
    </section>
  )
}

export function DeskToolsBar({ onOpen, beginnerMode, onToggleBeginner, symbol, extra }) {
  const tools = [
    { id: 'compare', label: 'Compare' },
    { id: 'ask', label: 'Ask' },
    { id: 'practice', label: 'Practice' },
    { id: 'size', label: 'Size' },
    { id: 'journal', label: 'Journal' },
    { id: 'export', label: 'Export' },
  ]
  return (
    <div className="desk-tools-bar">
      <div className="desk-tool-chips">
        {tools.map(t => (
          <button key={t.id} type="button" className="desk-tool-chip ghost" onClick={() => onOpen(t.id)}>
            {t.label}
          </button>
        ))}
      </div>
      <div className="desk-tools-right">
        {extra}
        <label className="beginner-toggle refresh-toggle">
          <input type="checkbox" checked={beginnerMode} onChange={e => onToggleBeginner(e.target.checked)} />
          Beginner mode
        </label>
        {symbol && <span className="subtle">{symbol}</span>}
      </div>
    </div>
  )
}

function DeskModal({ open, onClose, title, children, wide }) {
  if (!open) return null
  return (
    <div className="genai-modal-backdrop" role="dialog" aria-modal="true" aria-label={title}>
      <div className={`genai-modal desk-tool-modal${wide ? ' desk-tool-modal--wide' : ''}`}>
        <section className="panel">
          <div className="panel-head">
            <div><p className="eyebrow">DESK TOOL</p><h3>{title}</h3></div>
            <button type="button" className="ghost" onClick={onClose}>Close</button>
          </div>
          <div className="desk-tool-body">{children}</div>
        </section>
      </div>
    </div>
  )
}

function AskFormBody({ symbol, provider, onError, compact }) {
  const [question, setQuestion] = useState('')
  const [useSymbol, setUseSymbol] = useState(true)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)

  async function submit(q = question) {
    const cleaned = (q || '').trim()
    if (cleaned.length < 5) return onError('Ask a longer question (at least 5 characters).')
    onError('')
    setBusy(true)
    try {
      const data = await apiPost('/api/rag/ask', {
        question: cleaned,
        symbol: useSymbol && symbol ? symbol : null,
        provider,
      })
      setResult(data)
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={compact ? 'form-stack' : 'desk-tool-form'}>
      {!compact && (
        <div className="desk-tool-presets">
          {ASK_PRESETS.map(p => (
            <button key={p} type="button" className="ghost desk-tool-chip" onClick={() => { setQuestion(p); submit(p) }}>
              {p}
            </button>
          ))}
        </div>
      )}
      <label>
        Question
        <textarea rows={compact ? 3 : 4} value={question} onChange={e => setQuestion(e.target.value)} placeholder="Ask about risk, indicators, or process…" />
      </label>
      <div className="desk-tool-form-actions">
        {symbol && (
          <label className="refresh-toggle">
            <input type="checkbox" checked={useSymbol} onChange={e => setUseSymbol(e.target.checked)} />
            Include {symbol} context
          </label>
        )}
        <button type="button" className="primary" disabled={busy} onClick={() => submit()}>
          {busy ? 'Thinking…' : 'Ask'}
        </button>
      </div>
      {result && (
        <div className="ai-card">
          <p>{result.answer}</p>
          {(result.bullets || []).length > 0 && (
            <ul className="reason-list compact">
              {result.bullets.map((b, i) => <li key={i}>{b}</li>)}
            </ul>
          )}
          {(result.caveats || []).length > 0 && (
            <p className="subtle">{(result.caveats || []).join(' · ')}</p>
          )}
          {(result.retrieved_sources || []).length > 0 && (
            <div className="subtle">
              <p className="eyebrow">Sources</p>
              <ul className="reason-list compact">
                {result.retrieved_sources.map((s, i) => (
                  <li key={i}>{s.source} p.{s.page} chunk {s.chunk}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function PracticeFormBody({ symbol, provider, onError, compact }) {
  const [symbolsText, setSymbolsText] = useState(symbol || '')
  const [capital, setCapital] = useState(100000)
  const [tradingDays, setTradingDays] = useState(10)
  const [withAi, setWithAi] = useState(true)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)

  async function run() {
    const syms = symbolsText.split(/[,;\s]+/).map(s => s.trim().toUpperCase()).filter(Boolean)
    if (!syms.length) return onError('Enter at least one symbol.')
    onError('')
    setBusy(true)
    try {
      const data = await apiPost('/api/paper-trade', {
        symbols: syms.slice(0, 4),
        provider,
        capital: Number(capital),
        trading_days: Number(tradingDays),
        with_ai: withAi,
      })
      setResult(data)
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const sim = result?.simulations?.[0]
  const lesson = (result?.lessons || [])[0]?.ai

  return (
    <div className={compact ? 'form-stack' : 'desk-tool-form'}>
      <div className="desk-tool-form-row desk-tool-form-row--3">
        <label>
          Symbols (comma-separated)
          <input value={symbolsText} onChange={e => setSymbolsText(e.target.value)} placeholder={symbol || 'RELIANCE.NSE'} />
        </label>
        <label>
          Capital
          <input type="number" min="1000" value={capital} onChange={e => setCapital(e.target.value)} />
        </label>
        <label>
          Trading days
          <input type="number" min="5" max="30" value={tradingDays} onChange={e => setTradingDays(e.target.value)} />
        </label>
      </div>
      <div className="desk-tool-form-actions">
        <label className="refresh-toggle">
          <input type="checkbox" checked={withAi} onChange={e => setWithAi(e.target.checked)} />
          AI lesson
        </label>
        <button type="button" className="primary" disabled={busy} onClick={run}>
          {busy ? 'Simulating…' : 'Run paper trade'}
        </button>
      </div>
      {sim && (
        <div className="paper-rank">
          <article className={sim.outcome === 'gain' ? 'gain' : sim.outcome === 'loss' ? 'loss' : ''}>
            <p className="eyebrow">P&L</p>
            <h3 className={sim.pnl >= 0 ? 'up' : 'down'}>
              {sim.pnl_pct != null ? `${number.format(sim.pnl_pct)}%` : '—'}
            </h3>
            <p>{money.format(sim.pnl || 0)}</p>
          </article>
          <article>
            <p className="eyebrow">MAX DRAWDOWN</p>
            <h3>{sim.max_drawdown_pct != null ? `${number.format(sim.max_drawdown_pct)}%` : '—'}</h3>
          </article>
        </div>
      )}
      {sim?.equity_curve?.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Date</th><th>Equity</th><th>P&L %</th></tr></thead>
            <tbody>
              {sim.equity_curve.slice(-6).map(row => (
                <tr key={row.date}>
                  <td>{row.date}</td>
                  <td>{money.format(row.equity)}</td>
                  <td className={(row.pnl_pct ?? 0) >= 0 ? 'up' : 'down'}>{number.format(row.pnl_pct)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {lesson && (
        <div className="ai-card">
          <p className="eyebrow">AI LESSON</p>
          <h4>{lesson.headline}</h4>
          <p>{lesson.lesson}</p>
        </div>
      )}
      {result?.ranking?.winner_symbol && result.simulations?.length > 1 && (
        <p className="subtle">Winner: {result.ranking.winner_symbol} ({number.format(result.ranking.winner_pnl_pct)}%)</p>
      )}
    </div>
  )
}

export function CompareModal({ open, onClose, leftSymbol, rightSymbol, provider, onError, onAnalyze }) {
  const [left, setLeft] = useState(leftSymbol || '')
  const [right, setRight] = useState(rightSymbol || 'TCS.NSE')
  const [withAi, setWithAi] = useState(true)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)

  useEffect(() => {
    if (leftSymbol) setLeft(leftSymbol)
  }, [leftSymbol])

  useEffect(() => {
    if (rightSymbol) setRight(rightSymbol)
  }, [rightSymbol])

  async function compare() {
    if (!left.trim() || !right.trim()) return onError('Enter both symbols.')
    onError('')
    setBusy(true)
    try {
      const data = await apiPost('/api/compare', {
        left_symbol: left.trim().toUpperCase(),
        right_symbol: right.trim().toUpperCase(),
        provider,
        with_ai: withAi,
      })
      setResult(data)
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const ai = result?.ai

  return (
    <DeskModal open={open} onClose={onClose} title="Compare stocks" wide>
      <div className="desk-tool-form">
        <div className="desk-tool-form-row">
          <label>
            Left
            <input value={left} onChange={e => setLeft(e.target.value)} />
          </label>
          <label>
            Right
            <input value={right} onChange={e => setRight(e.target.value)} />
          </label>
        </div>
        <div className="desk-tool-form-actions">
          <label className="refresh-toggle">
            <input type="checkbox" checked={withAi} onChange={e => setWithAi(e.target.checked)} />
            With AI summary
          </label>
          <button type="button" className="primary" disabled={busy} onClick={compare}>
            {busy ? 'Comparing…' : 'Compare'}
          </button>
        </div>
        {result?.tally && (
          <p className="desk-tool-tally">
            Left wins {result.tally.left_metric_wins} · Right wins {result.tally.right_metric_wins} · Ties {result.tally.ties_or_missing}
          </p>
        )}
        {result?.scorecard?.length > 0 && (
          <div className="desk-tool-table-wrap table-wrap">
            <table>
              <thead>
                <tr><th>Metric</th><th>{result.left?.ticker || left}</th><th>{result.right?.ticker || right}</th><th>Edge</th></tr>
              </thead>
              <tbody>
                {result.scorecard.map((row, i) => (
                  <tr key={i}>
                    <td>{row.metric}</td>
                    <td>{row.left != null ? number.format(row.left) : '—'}</td>
                    <td>{row.right != null ? number.format(row.right) : '—'}</td>
                    <td>{row.edge === 'a' ? 'Left' : row.edge === 'b' ? 'Right' : 'Tie'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {ai && (
          <div className="ai-card">
            <p className="eyebrow">WINNER · {ai.winner}</p>
            <p>{ai.summary}</p>
            {ai.risk_note && <p className="subtle">{ai.risk_note}</p>}
          </div>
        )}
        {onAnalyze && (
          <div className="feature-controls">
            <button type="button" className="ghost" onClick={() => onAnalyze(left.trim().toUpperCase())}>Analyze left</button>
            <button type="button" className="ghost" onClick={() => onAnalyze(right.trim().toUpperCase())}>Analyze right</button>
          </div>
        )}
      </div>
    </DeskModal>
  )
}

export function AskModal({ open, onClose, symbol, provider, onError }) {
  return (
    <DeskModal open={open} onClose={onClose} title="Ask research desk">
      <AskFormBody symbol={symbol} provider={provider} onError={onError} />
    </DeskModal>
  )
}

export function PracticeModal({ open, onClose, symbol, provider, onError }) {
  return (
    <DeskModal open={open} onClose={onClose} title="Paper trade practice">
      <PracticeFormBody symbol={symbol} provider={provider} onError={onError} />
    </DeskModal>
  )
}

export function SizeModal({ open, onClose, analysis, onError, onApplyShares }) {
  const hint = analysis?.position_size_hint
  const tech = analysis?.technicals || {}
  const [capital, setCapital] = useState(hint?.capital ?? 100000)
  const [riskPct, setRiskPct] = useState(hint?.risk_pct ?? 1)
  const [atrMult, setAtrMult] = useState(hint?.atr_stop_mult ?? 1.5)
  const [rewardR, setRewardR] = useState(hint?.reward_r ?? 2)
  const [sizing, setSizing] = useState(hint)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (hint) setSizing(hint)
  }, [hint])

  async function recalc() {
    const price = Number(tech.price || hint?.price || 0)
    const atr = tech.volatility?.atr_14 ?? hint?.atr
    if (!price) return onError('No price available for sizing.')
    onError('')
    setBusy(true)
    try {
      const data = await apiPost('/api/desk/position-size', {
        price,
        atr: atr || null,
        capital: Number(capital),
        risk_pct: Number(riskPct),
        atr_stop_mult: Number(atrMult),
        reward_r: Number(rewardR),
      })
      setSizing(data)
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <DeskModal open={open} onClose={onClose} title="Position size">
      <div className="desk-tool-form">
        <div className="desk-tool-form-row">
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
            ATR stop mult
            <input type="number" min="0.5" max="4" step="0.1" value={atrMult} onChange={e => setAtrMult(e.target.value)} />
          </label>
          <label>
            Reward (R)
            <input type="number" min="0.5" max="5" step="0.5" value={rewardR} onChange={e => setRewardR(e.target.value)} />
          </label>
        </div>
        <div className="desk-tool-form-actions">
          <button type="button" className="ghost" disabled={busy} onClick={recalc}>
            {busy ? 'Recalculating…' : 'Recalculate'}
          </button>
        </div>
        {sizing && (
          <div className="ai-card">
            <p><b>{sizing.shares ?? 0}</b> shares · stop {sizing.stop_price != null ? money.format(sizing.stop_price) : '—'}</p>
            <p>Notional {money.format(sizing.notional || 0)} · heat {sizing.position_heat_pct ?? '—'}%</p>
            {(sizing.targets || []).length > 0 && (
              <p className="subtle">
                Targets:{' '}
                {sizing.targets.map(t => `${t.r}R ₹${number.format(t.price)}`).join(' · ')}
              </p>
            )}
            <p className="subtle">{sizing.plain}</p>
          </div>
        )}
        {sizing?.shares > 0 && onApplyShares && (
          <button type="button" className="primary" onClick={() => onApplyShares(sizing.shares)}>
            Use shares in Purchase
          </button>
        )}
      </div>
    </DeskModal>
  )
}

export function JournalModal({ open, onClose, symbol }) {
  const [notes, setNotes] = useState(() => loadStore(JOURNAL_KEY, []))
  const [stance, setStance] = useState('wait')
  const [text, setText] = useState('')
  const [filter, setFilter] = useState(symbol || 'all')

  useEffect(() => {
    saveStore(JOURNAL_KEY, notes)
  }, [notes])

  function addNote() {
    if (!text.trim()) return
    const entry = {
      id: `${Date.now()}`,
      symbol: symbol || '—',
      stance,
      text: text.trim(),
      date: new Date().toISOString(),
    }
    setNotes(prev => [entry, ...prev].slice(0, 200))
    setText('')
  }

  function deleteNote(id) {
    setNotes(prev => prev.filter(n => n.id !== id))
  }

  const visible = filter === 'all'
    ? notes
    : notes.filter(n => n.symbol === filter)

  return (
    <DeskModal open={open} onClose={onClose} title="Trade journal">
      <div className="desk-tool-form">
        <div className="desk-tool-form-row">
          <label>
            Stance
            <select value={stance} onChange={e => setStance(e.target.value)}>
              <option value="buy">Buy</option>
              <option value="wait">Wait</option>
              <option value="avoid">Avoid</option>
            </select>
          </label>
          <label>
            Note
            <textarea rows={3} value={text} onChange={e => setText(e.target.value)} placeholder="What you saw, plan, or lesson…" />
          </label>
        </div>
        <div className="desk-tool-form-actions">
          <button type="button" className="primary" onClick={addNote}>Add note</button>
          <div className="feature-controls">
            <button type="button" className={`ghost ${filter === 'all' ? 'primary' : ''}`} onClick={() => setFilter('all')}>All</button>
            {symbol && (
              <button type="button" className={`ghost ${filter === symbol ? 'primary' : ''}`} onClick={() => setFilter(symbol)}>
                {symbol}
              </button>
            )}
          </div>
        </div>
        <ul className="reason-list compact">
          {visible.length === 0 && <li className="subtle">No notes yet.</li>}
          {visible.map(n => (
            <li key={n.id}>
              <b>{n.symbol}</b> · {n.stance} · {new Date(n.date).toLocaleDateString('en-IN')}
              <br />{n.text}
              <button type="button" className="ghost" onClick={() => deleteNote(n.id)}>Delete</button>
            </li>
          ))}
        </ul>
      </div>
    </DeskModal>
  )
}

export function PreBuyChecklist({ analysis, accepted, setAccepted }) {
  const tech = analysis?.technicals || {}
  const rsi = tech.momentum?.rsi_14
  const redCount = (analysis?.dossier?.signal_radar?.red_flags || []).length
  const eventCount = analysis?.event_watch?.count ?? (analysis?.event_watch?.items || []).length

  const items = useMemo(() => [
    {
      id: 'concentration',
      label: 'I understand adding one stock can increase concentration risk in my portfolio.',
    },
    {
      id: 'rsi',
      label: rsi != null && rsi >= 70
        ? `RSI is ${number.format(rsi)} (overbought zone) — momentum may be stretched.`
        : 'I have reviewed momentum (RSI) on this name.',
      show: true,
    },
    {
      id: 'redflags',
      label: redCount > 0
        ? `I have read ${redCount} red flag(s) in the dossier.`
        : 'No dossier red flags flagged — I still accept general market risk.',
      show: true,
    },
    {
      id: 'events',
      label: eventCount > 0
        ? `I am aware of ${eventCount} event / catalyst item(s) on the watch list.`
        : 'I will monitor news and events around this holding.',
      show: true,
    },
    {
      id: 'disclaimer',
      label: 'This is educational paper trading only — not investment advice or a broker order.',
      show: true,
    },
  ].filter(i => i.show), [rsi, redCount, eventCount])

  const [checked, setChecked] = useState(() => Object.fromEntries(items.map(i => [i.id, false])))

  useEffect(() => {
    setChecked(Object.fromEntries(items.map(i => [i.id, false])))
  }, [items])

  useEffect(() => {
    const all = items.every(i => checked[i.id])
    setAccepted(all)
  }, [checked, items, setAccepted])

  return (
    <section className="panel prebuy-check">
      <div className="panel-head">
        <div><p className="eyebrow">PRE-BUY</p><h3>Checklist</h3></div>
        <span className="subtle">{accepted ? 'Ready' : 'Tick all items'}</span>
      </div>
      {items.map(item => (
        <label key={item.id} className="refresh-toggle">
          <input
            type="checkbox"
            checked={checked[item.id] || false}
            onChange={e => setChecked(c => ({ ...c, [item.id]: e.target.checked }))}
          />
          {item.label}
        </label>
      ))}
    </section>
  )
}

export function EventWatchPanel({ events }) {
  const items = events?.items
  if (!items?.length) return null
  return (
    <section className="panel event-watch">
      <div className="panel-head">
        <div><p className="eyebrow">EVENT WATCH</p><h3>Catalysts & risks</h3></div>
        <span className="subtle">{items.length}</span>
      </div>
      <ul className="reason-list compact">
        {items.map((ev, i) => (
          <li key={i}>
            <span className="eyebrow">{ev.label || ev.tag}</span>
            {ev.url ? <a href={ev.url} target="_blank" rel="noreferrer">{ev.title}</a> : ev.title}
            {ev.when && <span className="subtle"> · {ev.when}</span>}
          </li>
        ))}
      </ul>
    </section>
  )
}

export function SectorHeatPanel({ heat, onAnalyze }) {
  const buckets = heat?.buckets || []
  if (!buckets.length) {
    return (
      <section className="panel">
        <div className="panel-head">
          <div><p className="eyebrow">SECTOR HEAT</p><h3>Universe buckets</h3></div>
        </div>
        <p className="subtle">{heat?.hint || 'Run Screener once to populate sector heat.'}</p>
      </section>
    )
  }
  const maxScore = Math.max(...buckets.map(b => b.avg_score || 0), 1)
  return (
    <section className="panel">
      <div className="panel-head">
        <div><p className="eyebrow">SECTOR HEAT</p><h3>Avg screen score</h3></div>
        <span className="subtle">{heat.count || buckets.length} sectors</span>
      </div>
      <div className="horizon-grid">
        {buckets.map(b => (
          <article key={b.sector} className="scenario-card">
            <p className="eyebrow">{b.sector}</p>
            <div style={{ background: '#243447', borderRadius: 4, height: 6, marginTop: 4 }}>
              <div style={{ width: `${(b.avg_score / maxScore) * 100}%`, background: '#6ea8fe', height: 6, borderRadius: 4 }} />
            </div>
            <p className="subtle">{number.format(b.avg_score)} · {b.count} names · {b.up} up / {b.down} down</p>
            {onAnalyze && b.sample_symbol && (
              <button type="button" className="ghost" onClick={() => onAnalyze(b.sample_symbol)}>Analyze</button>
            )}
          </article>
        ))}
      </div>
    </section>
  )
}

export function CustomWatchlist({ onAnalyze }) {
  const [list, setList] = useState(() => loadStore(WATCHLIST_KEY, []))
  const [input, setInput] = useState('')

  useEffect(() => {
    saveStore(WATCHLIST_KEY, list)
  }, [list])

  function add() {
    const sym = input.trim().toUpperCase()
    if (!sym || list.includes(sym)) return
    setList(prev => [...prev, sym])
    setInput('')
  }

  function remove(sym) {
    setList(prev => prev.filter(s => s !== sym))
  }

  return (
    <section className="panel custom-watch">
      <div className="panel-head">
        <div><p className="eyebrow">WATCHLIST</p><h3>Custom symbols</h3></div>
        <span className="subtle">{list.length}</span>
      </div>
      <div className="feature-controls">
        <input value={input} onChange={e => setInput(e.target.value)} placeholder="SYMBOL.NSE" />
        <button type="button" className="primary" onClick={add}>Add</button>
      </div>
      <ul className="reason-list compact">
        {list.length === 0 && <li className="subtle">Add symbols to track and analyze quickly.</li>}
        {list.map(sym => (
          <li key={sym}>
            <b>{sym}</b>
            {onAnalyze && <button type="button" className="ghost" onClick={() => onAnalyze(sym)}>Analyze</button>}
            <button type="button" className="ghost" onClick={() => remove(sym)}>Remove</button>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function CoachPage({ provider, onError, symbol, onAnalyze, advisorSlot }) {
  const [tab, setTab] = useState('advisor')
  const tabs = [
    { id: 'advisor', label: 'Advisor' },
    { id: 'ask', label: 'Ask' },
    { id: 'practice', label: 'Practice' },
    { id: 'glossary', label: 'Glossary' },
  ]

  return (
    <section className="panel coach-page">
      <div className="panel-head">
        <div><p className="eyebrow">COACH</p><h3>Learn & practice</h3></div>
        {symbol && <span className="subtle">{symbol}</span>}
      </div>
      <div className="coach-tabs feature-controls">
        {tabs.map(t => (
          <button
            key={t.id}
            type="button"
            className={tab === t.id ? 'primary' : 'ghost'}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'advisor' && advisorSlot}
      {tab === 'ask' && <AskFormBody symbol={symbol} provider={provider} onError={onError} compact />}
      {tab === 'practice' && <PracticeFormBody symbol={symbol} provider={provider} onError={onError} compact />}
      {tab === 'glossary' && (
        <div className="scenario-grid">
          {GLOSSARY.map(g => (
            <article key={g.title} className="scenario-card">
              <p className="eyebrow">{g.title}</p>
              <p>{g.body}</p>
            </article>
          ))}
        </div>
      )}
      {onAnalyze && symbol && tab !== 'advisor' && (
        <button type="button" className="ghost" onClick={() => onAnalyze(symbol)}>Analyze {symbol}</button>
      )}
    </section>
  )
}

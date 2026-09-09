import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { apiGet, apiPost, apiPostBlob, apiPostForm, brokerStreamWsUrl } from './lib/apiClient'
import { loadStore, saveStore } from './lib/storage'

const number = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 })
const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })

const NOTIFY_KEY = 'scanBhavNotify'
const RICH_JOURNAL_KEY = 'scanBhavRichJournal'
const CURRICULUM_KEY = 'scanBhavCurriculum'

const ACCOUNT_KEYS = [
  'scanBhavWizard',
  'scanBhavWatchlist',
  'scanBhavJournal',
  'scanBhavRichJournal',
  'scanBhavBeginner',
  'scanBhavLearn',
  'scanBhavNotify',
  'scanBhavCurriculum',
  'scanBhavSwingTrades',
  'scanBhavSwingWatchlist',
  'scanBhavSwingAlerts',
  'scanBhavSwingBroker',
  'scanBhavSettings',
]

const REMAINING_TOOLS = [
  { id: 'options', label: 'Options' },
  { id: 'earnings', label: 'Earnings' },
  { id: 'intraday', label: 'Intraday' },
  { id: 'correlation', label: 'Risk matrix' },
  { id: 'sector-rs', label: 'Sector RS' },
  { id: 'strategy', label: 'Strategy lab' },
  { id: 'journal', label: 'Journal+' },
  { id: 'export', label: 'Export' },
  { id: 'mf', label: 'MF' },
  { id: 'courses', label: 'Courses' },
  { id: 'sync', label: 'Sync' },
  { id: 'notify', label: 'Notify' },
]

function findVix(board) {
  return (board?.indices || []).find(i => /vix/i.test(`${i.id || ''} ${i.name || ''} ${i.label || ''}`))
}

function corrColor(value) {
  if (value == null || Number.isNaN(value)) return 'transparent'
  const v = Math.max(-1, Math.min(1, Number(value)))
  if (v >= 0) {
    const alpha = 0.15 + v * 0.45
    return `rgba(46, 207, 138, ${alpha})`
  }
  const alpha = 0.15 + Math.abs(v) * 0.45
  return `rgba(240, 113, 120, ${alpha})`
}

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

function buildMarkdownBrief(analysis, genaiResult) {
  if (!analysis) return ''
  const action = deriveAction(analysis)
  const dossier = analysis.dossier || {}
  const radar = dossier.signal_radar || {}
  const conviction = dossier.conviction || {}
  const tech = analysis.technicals || {}
  const ratings = analysis.ratings || {}
  const insight = genaiResult?.insight || genaiResult?.synthesis || null
  const lines = [`# ${analysis.symbol} — Research brief`]
  if (analysis.quote?.company?.name) lines.push(`**${analysis.quote.company.name}**`)
  lines.push('', '## Verdict', `- Action: **${action}**`, `- ${conviction.plain_english || 'No conviction note.'}`)
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
  return lines.join('\n')
}

export function RemainingModal({ open, onClose, title, children }) {
  if (!open) return null
  return (
    <div className="genai-modal-backdrop" role="dialog" aria-modal="true" aria-label={title}>
      <div className="genai-modal desk-tool-modal remaining-modal">
        <div className="remaining-modal-shell">
          <div className="panel-head">
            <div><p className="eyebrow">DESK TOOL</p><h3>{title}</h3></div>
            <button type="button" className="ghost" onClick={onClose}>Close</button>
          </div>
          <div className="remaining-modal-body">{children}</div>
        </div>
      </div>
    </div>
  )
}

export function RemainingToolsBar({ onOpen }) {
  return (
    <div className="desk-tools-bar">
      <div className="desk-tool-chips">
        {REMAINING_TOOLS.map(t => (
          <button key={t.id} type="button" className="desk-tool-chip ghost" onClick={() => onOpen(t.id)}>
            {t.label}
          </button>
        ))}
      </div>
    </div>
  )
}

export function LivePulse({
  symbol = '',
  onRefresh,
  onLtp,
  pollSeconds = 30,
  yahooPollSeconds = 15,
  autoRefresh = true,
  refreshOnLtp = false,
  ltpRefreshMs = 120000,
}) {
  const [live, setLive] = useState(true)
  const [wsState, setWsState] = useState('idle')
  const [transport, setTransport] = useState('')
  const [streamMeta, setStreamMeta] = useState(null)
  const [ltp, setLtp] = useState(null)
  const [countdown, setCountdown] = useState(pollSeconds)
  const wsRef = useRef(null)
  const onRefreshRef = useRef(onRefresh)
  const onLtpRef = useRef(onLtp)
  const lastAnalyzeRef = useRef(0)
  const autoRefreshRef = useRef(autoRefresh)
  const refreshOnLtpRef = useRef(refreshOnLtp)

  onRefreshRef.current = onRefresh
  onLtpRef.current = onLtp
  autoRefreshRef.current = autoRefresh
  refreshOnLtpRef.current = refreshOnLtp

  const subscribeSymbol = useCallback((ws, sym) => {
    if (!ws || ws.readyState !== WebSocket.OPEN || !sym) return
    ws.send(JSON.stringify({ action: 'subscribe', symbols: [sym] }))
  }, [])

  useEffect(() => {
    if (!live || !symbol) {
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
      setWsState('idle')
      return undefined
    }

    let cancelled = false
    let pingTimer = null
    let reconnectTimer = null

    function connect() {
      if (cancelled) return
      setWsState('connecting')
      const ws = new WebSocket(brokerStreamWsUrl())
      wsRef.current = ws

      ws.onopen = () => {
        if (cancelled) return
        setWsState('open')
        subscribeSymbol(ws, symbol)
        pingTimer = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send('ping')
        }, 25000)
      }

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data)
          if (msg.type === 'status') {
            setTransport(msg.transport || '')
            setStreamMeta(msg.stream || null)
          }
          if (msg.type === 'ltp' && symbolsMatch(msg.symbol, symbol)) {
            setLtp(msg.price)
            onLtpRef.current?.(msg.price, msg)
            const now = Date.now()
            if (refreshOnLtpRef.current && onRefreshRef.current && now - lastAnalyzeRef.current > ltpRefreshMs) {
              lastAnalyzeRef.current = now
              onRefreshRef.current()
            }
          }
        } catch {
          /* ignore malformed frames */
        }
      }

      ws.onclose = () => {
        setWsState('closed')
        if (pingTimer) clearInterval(pingTimer)
        if (!cancelled) reconnectTimer = setTimeout(connect, 4000)
      }

      ws.onerror = () => ws.close()
    }

    connect()

    return () => {
      cancelled = true
      if (pingTimer) clearInterval(pingTimer)
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [live, symbol, subscribeSymbol])

  useEffect(() => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN && symbol) subscribeSymbol(ws, symbol)
  }, [symbol, subscribeSymbol])

  useEffect(() => {
    if (!live || !onRefreshRef.current || !autoRefreshRef.current) {
      setCountdown(pollSeconds)
      return undefined
    }
    const intervalSec = transport === 'yahoo_poll' ? yahooPollSeconds : pollSeconds
    setCountdown(intervalSec)
    const tick = setInterval(() => {
      setCountdown(c => {
        if (c <= 1) {
          onRefreshRef.current?.()
          return intervalSec
        }
        return c - 1
      })
    }, 1000)
    return () => clearInterval(tick)
  }, [live, pollSeconds, yahooPollSeconds, transport, autoRefresh])

  const statusLabel = live
    ? wsState === 'open'
      ? transportLabel(transport, streamMeta)
      : wsState === 'connecting'
        ? 'Connecting stream…'
        : 'Reconnecting stream…'
    : 'Stream paused'

  return (
    <div className="feature-controls live-pulse" style={{ marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
      <label className="refresh-toggle">
        <input type="checkbox" checked={live} onChange={e => setLive(e.target.checked)} />
        Live stream
      </label>
      <span className={`live-dot ${wsState === 'open' ? 'on' : ''}`} title={statusLabel} aria-hidden />
      {ltp != null && symbol ? <strong>{formatInr(ltp)}</strong> : null}
      <span className="subtle">{statusLabel}</span>
      {live && onRefresh && autoRefresh ? <span className="subtle">Full chart refresh in {countdown}s</span> : null}
      <button type="button" className="ghost" onClick={() => onRefreshRef.current?.()}>Refresh now</button>
    </div>
  )
}

function symbolBase(sym) {
  return String(sym || '').toUpperCase().split('.')[0]
}

function symbolsMatch(a, b) {
  const A = String(a || '').toUpperCase()
  const B = String(b || '').toUpperCase()
  if (!A || !B) return false
  if (A === B) return true
  return symbolBase(A) === symbolBase(B)
}

function formatInr(price) {
  if (price == null || Number.isNaN(Number(price))) return '—'
  return money.format(Number(price))
}

function transportLabel(transport, stream) {
  if (transport === 'websocket') return 'Zerodha WebSocket · tick LTP'
  if (transport === 'rest_poll') {
    return `${(stream?.broker || 'Broker').toString()} REST ~${stream?.interval_seconds || 3}s`
  }
  if (transport === 'yahoo_poll') return `Yahoo/NSE ~${stream?.interval_seconds || 15}s (no broker keys)`
  return 'Waiting for stream status…'
}

export function OptionsDesk({ symbol, analysis, marketBoard }) {
  const [busy, setBusy] = useState(false)
  const [pulse, setPulse] = useState(null)
  const [error, setError] = useState('')

  const vix = findVix(marketBoard)
  const tech = analysis?.technicals || {}

  useEffect(() => {
    if (!symbol) return
    let cancelled = false
    async function load() {
      setBusy(true)
      setError('')
      try {
        const data = await apiPost('/api/desk/options-pulse', {
          symbol,
          price: tech.price,
          atr: tech.volatility?.atr_14,
          vix: vix?.price ?? vix?.value,
        })
        if (!cancelled) setPulse(data)
      } catch (err) {
        if (!cancelled) setError(err.message)
      } finally {
        if (!cancelled) setBusy(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [symbol, tech.price, tech.volatility?.atr_14, vix?.price, vix?.value])

  const cards = pulse?.cards || pulse?.insights || []

  return (
    <section className="panel">
      <div className="panel-head">
        <div><p className="eyebrow">OPTIONS PULSE</p><h3>Educational context</h3></div>
        {symbol && <span className="subtle">{symbol}</span>}
      </div>
      {busy && <p className="subtle">Loading options pulse…</p>}
      {error && <p className="subtle">{error}</p>}
      {pulse?.plain && <p>{pulse.plain}</p>}
      {pulse?.stance && (
        <p className="subtle">Stance: <strong>{pulse.stance}</strong></p>
      )}
      {pulse?.vix_context && (
        <p className="subtle">VIX: {pulse.vix_context}</p>
      )}
      {pulse?.straddle_range && (
        <p className="subtle">
          ATM straddle (conceptual): {money.format(pulse.straddle_range.low)} – {money.format(pulse.straddle_range.high)}
        </p>
      )}
      {cards.length > 0 && (
        <div className="horizon-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))' }}>
          {cards.map((card, i) => (
            <article key={i} className="scenario-card">
              <p className="eyebrow">{card.title || card.label || 'Note'}</p>
              <p>{card.body || card.text || card.plain}</p>
            </article>
          ))}
        </div>
      )}
      <p className="subtle">{pulse?.disclaimer || 'PCR/OI require live NFO feed — educational ranges only.'}</p>
    </section>
  )
}

export function EarningsCalendar({ symbol }) {
  const [events, setEvents] = useState([])
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!symbol) return
    let cancelled = false
    async function load() {
      setBusy(true)
      try {
        const data = await apiGet(`/api/desk/earnings/${encodeURIComponent(symbol)}`)
        if (!cancelled) {
          setEvents(data.events || data.items || [])
          setNote(data.note || data.plain || '')
        }
      } catch (err) {
        if (!cancelled) {
          setEvents([])
          setNote(err.message)
        }
      } finally {
        if (!cancelled) setBusy(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [symbol])

  return (
    <section className="panel">
      <div className="panel-head">
        <div><p className="eyebrow">EARNINGS</p><h3>Event calendar</h3></div>
        {symbol && <span className="subtle">{symbol}</span>}
      </div>
      {busy && <p className="subtle">Loading calendar…</p>}
      {note && !events.length && <p className="subtle">{note}</p>}
      <ul className="reason-list compact">
        {events.length === 0 && !busy && <li className="subtle">No upcoming events found.</li>}
        {events.map((ev, i) => (
          <li key={i}>
            <strong>{ev.date || ev.when || '—'}</strong>
            {' · '}{ev.event || ev.title || ev.label || 'Event'}
            {ev.estimate != null && <span className="subtle"> · est {number.format(ev.estimate)}</span>}
          </li>
        ))}
      </ul>
    </section>
  )
}

export function IntradayLevelsPanel({ symbol, provider }) {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    if (!symbol) return
    setBusy(true)
    setError('')
    try {
      const qs = provider ? `?provider=${encodeURIComponent(provider)}` : ''
      const payload = await apiGet(`/api/desk/intraday/${encodeURIComponent(symbol)}${qs}`)
      setData(payload)
    } catch (err) {
      setError(err.message)
      setData(null)
    } finally {
      setBusy(false)
    }
  }, [symbol, provider])

  useEffect(() => { load() }, [load])

  const orb = data?.opening_range || data?.orb || data?.opening_range_proxy
  const vwap = data?.vwap ?? data?.session_vwap

  return (
    <section className="panel">
      <div className="panel-head">
        <div><p className="eyebrow">INTRADAY</p><h3>Session levels</h3></div>
        <button type="button" className="ghost" disabled={busy} onClick={load}>Refresh</button>
      </div>
      <LivePulse symbol={symbol} onRefresh={load} />
      {busy && <p className="subtle">Fetching intraday bars…</p>}
      {error && <p className="subtle">{error}</p>}
      {data?.plain && <p>{data.plain}</p>}
      <div className="metrics">
        <article className="metric">
          <p>Gap</p>
          <strong className={(data?.gap_pct ?? 0) >= 0 ? 'up' : 'down'}>
            {data?.gap_pct != null ? `${data.gap_pct >= 0 ? '+' : ''}${number.format(data.gap_pct)}%` : '—'}
          </strong>
        </article>
        <article className="metric">
          <p>VWAP</p>
          <strong>{vwap != null ? number.format(vwap) : '—'}</strong>
        </article>
        <article className="metric">
          <p>ORB high</p>
          <strong>{orb?.high != null ? number.format(orb.high) : '—'}</strong>
        </article>
        <article className="metric">
          <p>ORB low</p>
          <strong>{orb?.low != null ? number.format(orb.low) : '—'}</strong>
        </article>
      </div>
      {orb?.note && <p className="subtle">{orb.note}</p>}
      {data?.gap_filled != null && (
        <p className="subtle">Gap filled: {data.gap_filled ? 'Yes' : 'No'}</p>
      )}
    </section>
  )
}

export function NotifySettings({ alerts }) {
  const [settings, setSettings] = useState(() => loadStore(NOTIFY_KEY, {
    webhook_url: '',
    telegram_bot_token: '',
    telegram_chat_id: '',
  }))
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('')

  useEffect(() => {
    saveStore(NOTIFY_KEY, settings)
  }, [settings])

  async function send() {
    setBusy(true)
    setStatus('')
    try {
      const data = await apiPost('/api/desk/notify', {
        alerts: alerts || [],
        webhook_url: settings.webhook_url || undefined,
        telegram_bot_token: settings.telegram_bot_token || undefined,
        telegram_chat_id: settings.telegram_chat_id || undefined,
      })
      setStatus(data.sent ? `Sent (${data.sent} channel(s))` : 'Dispatch attempted')
      if (data.errors?.length) setStatus(prev => `${prev} · ${data.errors.join('; ')}`)
    } catch (err) {
      setStatus(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <div><p className="eyebrow">NOTIFY</p><h3>Webhook & Telegram</h3></div>
        <span className="subtle">{alerts?.length || 0} alert(s)</span>
      </div>
      <div className="buy-grid">
        <label>
          Webhook URL
          <input
            type="url"
            value={settings.webhook_url}
            onChange={e => setSettings(s => ({ ...s, webhook_url: e.target.value }))}
            placeholder="https://hooks.example.com/…"
          />
        </label>
        <label>
          Telegram bot token (optional)
          <input
            type="password"
            value={settings.telegram_bot_token}
            onChange={e => setSettings(s => ({ ...s, telegram_bot_token: e.target.value }))}
            placeholder="123456:ABC…"
          />
        </label>
        <label>
          Telegram chat ID (optional)
          <input
            type="text"
            value={settings.telegram_chat_id}
            onChange={e => setSettings(s => ({ ...s, telegram_chat_id: e.target.value }))}
            placeholder="-100…"
          />
        </label>
      </div>
      <button type="button" className="primary" disabled={busy} onClick={send}>
        {busy ? 'Sending…' : 'Send alerts now'}
      </button>
      {status && <p className="subtle">{status}</p>}
      <p className="subtle">Settings saved locally. Do not commit tokens to git.</p>
    </section>
  )
}

export function CorrelationMatrix({ symbols, provider, onError }) {
  const [matrix, setMatrix] = useState(null)
  const [busy, setBusy] = useState(false)

  const symList = useMemo(
    () => (symbols || []).filter(Boolean).slice(0, 8),
    [symbols],
  )

  useEffect(() => {
    if (symList.length < 2) {
      setMatrix(null)
      return
    }
    let cancelled = false
    async function load() {
      setBusy(true)
      onError?.('')
      try {
        const data = await apiPost('/api/desk/correlation', { symbols: symList, provider })
        if (!cancelled) setMatrix(data)
      } catch (err) {
        onError?.(err.message)
        if (!cancelled) setMatrix(null)
      } finally {
        if (!cancelled) setBusy(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [symList, provider, onError])

  const pairs = matrix?.pairs || matrix?.matrix || []
  const labels = matrix?.symbols || symList

  const lookup = useMemo(() => {
    const map = new Map()
    for (const p of pairs) {
      const a = p.a || p.symbol_a
      const b = p.b || p.symbol_b
      const key = `${a}|${b}`
      map.set(key, p.corr ?? p.correlation)
      map.set(`${b}|${a}`, p.corr ?? p.correlation)
    }
    return map
  }, [pairs])

  if (symList.length < 2) {
    return (
      <section className="panel">
        <div className="panel-head">
          <div><p className="eyebrow">CORRELATION</p><h3>Risk matrix</h3></div>
        </div>
        <p className="subtle">Add at least two symbols to compare pairwise correlation.</p>
      </section>
    )
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <div><p className="eyebrow">CORRELATION</p><h3>Pairwise matrix</h3></div>
        {busy && <span className="subtle">Computing…</span>}
      </div>
      {matrix?.plain && <p className="subtle">{matrix.plain}</p>}
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', padding: 6 }} />
              {labels.map(s => (
                <th key={s} style={{ padding: 6, fontWeight: 600 }}>{s.replace(/\.(NSE|BSE)$/, '')}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {labels.map(row => (
              <tr key={row}>
                <td style={{ padding: 6, fontWeight: 600 }}>{row.replace(/\.(NSE|BSE)$/, '')}</td>
                {labels.map(col => {
                  const val = row === col ? 1 : lookup.get(`${row}|${col}`)
                  return (
                    <td
                      key={col}
                      style={{
                        padding: 6,
                        textAlign: 'center',
                        background: corrColor(val),
                        border: '1px solid rgba(36,52,71,0.6)',
                      }}
                    >
                      {val != null ? number.format(val) : '—'}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export function SectorRsPanel({ onAnalyze }) {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setBusy(true)
    try {
      const payload = await apiGet('/api/desk/sector-rs')
      setData(payload)
    } catch {
      setData(null)
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const sectors = data?.sectors || data?.ranked || data?.buckets || []

  return (
    <section className="panel">
      <div className="panel-head">
        <div><p className="eyebrow">SECTOR RS</p><h3>Relative strength rank</h3></div>
        <button type="button" className="ghost" disabled={busy} onClick={load}>Refresh</button>
      </div>
      {data?.plain && <p className="subtle">{data.plain}</p>}
      {sectors.length === 0 && !busy && (
        <p className="subtle">{data?.hint || 'Run Screener once to populate sector RS.'}</p>
      )}
      <ul className="reason-list compact">
        {sectors.map((s, i) => (
          <li key={s.sector || s.name || i}>
            <strong>{i + 1}. {s.sector || s.name}</strong>
            {s.avg_return_pct != null && (
              <span className={(s.avg_return_pct ?? 0) >= 0 ? 'up' : 'down'}>
                {' '}{s.avg_return_pct >= 0 ? '+' : ''}{number.format(s.avg_return_pct)}%
              </span>
            )}
            {s.vs_bench_pct != null && (
              <span className="subtle"> · vs bench {s.vs_bench_pct >= 0 ? '+' : ''}{number.format(s.vs_bench_pct)}%</span>
            )}
            {s.count != null && <span className="subtle"> · {s.count} names</span>}
            {onAnalyze && s.sample_symbol && (
              <>
                {' · '}
                <button type="button" className="linkish" onClick={() => onAnalyze(s.sample_symbol)}>
                  {s.sample_symbol.replace(/\.(NSE|BSE)$/, '')}
                </button>
              </>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

export function ChartDrawTools({ enabled, onChange }) {
  const [mode, setMode] = useState('off')

  useEffect(() => {
    if (!enabled && mode !== 'off') {
      setMode('off')
      onChange?.('off')
    }
  }, [enabled, mode, onChange])

  function pick(next) {
    setMode(next)
    onChange?.(next)
  }

  const help = mode === 'horizontal'
    ? 'Click chart to mark horizontal price levels (or use Add level below).'
    : mode === 'trend'
      ? 'Trend mode stores price anchors — pair with horizontal levels for simple plans.'
      : 'Drawing off — select a tool to annotate price levels.'

  return (
    <div className="chart-toolbar">
      <span className="subtle">Draw:</span>
      {['off', 'horizontal', 'trend'].map(m => (
        <button
          key={m}
          type="button"
          className={`ghost chart-tf${mode === m ? ' active' : ''}`}
          disabled={!enabled}
          onClick={() => pick(m)}
        >
          {m === 'off' ? 'Off' : m === 'horizontal' ? 'Horizontal' : 'Trend'}
        </button>
      ))}
      <span className="subtle">{help}</span>
    </div>
  )
}

export function useChartDrawings(candles) {
  const [mode, setMode] = useState('off')
  const [lines, setLines] = useState([])

  const onChartClick = useCallback((price) => {
    if (mode === 'off' || price == null) return
    const p = Number(price)
    if (!Number.isFinite(p)) return
    setLines(prev => [...prev, { id: `${Date.now()}-${prev.length}`, mode, price: p }].slice(-12))
  }, [mode])

  const clear = useCallback(() => setLines([]), [])

  return useMemo(() => ({
    mode,
    setMode,
    lines,
    onChartClick,
    clear,
    candles,
  }), [mode, lines, onChartClick, clear, candles])
}

export function PriceLevelDrawer({ levels, setLevels }) {
  const [input, setInput] = useState('')

  function addLevel() {
    const p = Number(input)
    if (!Number.isFinite(p) || p <= 0) return
    setLevels(prev => [...(prev || []), { id: `${Date.now()}`, price: p }].slice(-20))
    setInput('')
  }

  function removeLevel(id) {
    setLevels(prev => (prev || []).filter(l => l.id !== id))
  }

  return (
    <div className="buy-grid">
      <label>
        Add level
        <input
          type="number"
          step="any"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="Price"
          onKeyDown={e => e.key === 'Enter' && addLevel()}
        />
      </label>
      <button type="button" className="primary" onClick={addLevel}>Add</button>
      <ul className="reason-list compact">
        {(levels || []).length === 0 && <li className="subtle">No price levels yet.</li>}
        {(levels || []).map(l => (
          <li key={l.id}>
            {money.format(l.price)}
            <button type="button" className="ghost" onClick={() => removeLevel(l.id)}>Remove</button>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function StrategyLab({ symbol, provider, onError }) {
  const [strategy, setStrategy] = useState('sma_cross')
  const [capital, setCapital] = useState(100000)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)

  async function runSweep() {
    if (!symbol) return onError?.('Analyze a symbol first.')
    onError?.('')
    setBusy(true)
    try {
      const data = await apiPost('/api/desk/backtest-sweep', {
        symbol, provider, strategy, capital: Number(capital),
      })
      setResult(data)
    } catch (err) {
      onError?.(err.message)
    } finally {
      setBusy(false)
    }
  }

  const ranked = result?.ranked || result?.results || []

  return (
    <section className="panel backtest-panel">
      <div className="panel-head">
        <div><p className="eyebrow">STRATEGY LAB</p><h3>Parameter sweep</h3></div>
        {symbol && <span className="subtle">{symbol}</span>}
      </div>
      <div className="buy-grid">
        <label>
          Strategy
          <select value={strategy} onChange={e => setStrategy(e.target.value)}>
            <option value="sma_cross">SMA cross</option>
          </select>
        </label>
        <label>
          Capital
          <input type="number" min={1000} value={capital} onChange={e => setCapital(e.target.value)} />
        </label>
      </div>
      <button type="button" className="primary" disabled={busy || !symbol} onClick={runSweep}>
        {busy ? 'Sweeping…' : 'Backtest + Sweep'}
      </button>
      {result?.plain && <p className="subtle">{result.plain}</p>}
      {ranked.length > 0 && (
        <div style={{ overflowX: 'auto', marginTop: 12 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', padding: 6 }}>#</th>
                <th style={{ textAlign: 'left', padding: 6 }}>Fast</th>
                <th style={{ textAlign: 'left', padding: 6 }}>Slow</th>
                <th style={{ textAlign: 'right', padding: 6 }}>Return</th>
                <th style={{ textAlign: 'right', padding: 6 }}>Max DD</th>
                <th style={{ textAlign: 'right', padding: 6 }}>Win rate</th>
              </tr>
            </thead>
            <tbody>
              {ranked.map((row, i) => (
                <tr key={i}>
                  <td style={{ padding: 6 }}>{i + 1}</td>
                  <td style={{ padding: 6 }}>{row.fast ?? row.fast_period ?? '—'}</td>
                  <td style={{ padding: 6 }}>{row.slow ?? row.slow_period ?? '—'}</td>
                  <td style={{ padding: 6, textAlign: 'right' }} className={(row.return_pct ?? 0) >= 0 ? 'up' : 'down'}>
                    {row.return_pct != null ? `${number.format(row.return_pct)}%` : '—'}
                  </td>
                  <td style={{ padding: 6, textAlign: 'right' }}>{row.max_drawdown_pct != null ? `${number.format(row.max_drawdown_pct)}%` : '—'}</td>
                  <td style={{ padding: 6, textAlign: 'right' }}>{row.win_rate_pct != null ? `${number.format(row.win_rate_pct)}%` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

export function RichJournal({ symbol }) {
  const [entries, setEntries] = useState(() => loadStore(RICH_JOURNAL_KEY, []))
  const [filter, setFilter] = useState(symbol || 'all')
  const [draft, setDraft] = useState({
    tags: '',
    entry: '',
    exit: '',
    thesis: '',
    postmortem: '',
  })

  useEffect(() => {
    saveStore(RICH_JOURNAL_KEY, entries)
  }, [entries])

  function addEntry() {
    if (!draft.thesis.trim() && !draft.entry.trim()) return
    const entry = {
      id: `${Date.now()}`,
      symbol: symbol || '—',
      tags: draft.tags.split(',').map(t => t.trim()).filter(Boolean),
      entry: draft.entry.trim(),
      exit: draft.exit.trim(),
      thesis: draft.thesis.trim(),
      postmortem: draft.postmortem.trim(),
      date: new Date().toISOString(),
    }
    setEntries(prev => [entry, ...prev].slice(0, 200))
    setDraft({ tags: '', entry: '', exit: '', thesis: '', postmortem: '' })
  }

  function deleteEntry(id) {
    setEntries(prev => prev.filter(e => e.id !== id))
  }

  const visible = filter === 'all'
    ? entries
    : entries.filter(e => e.symbol === filter)

  return (
    <section className="panel">
      <div className="panel-head">
        <div><p className="eyebrow">JOURNAL+</p><h3>Rich trade log</h3></div>
        <span className="subtle">{visible.length} entries</span>
      </div>
      <div className="buy-grid">
        <label>
          Tags (comma-separated)
          <input value={draft.tags} onChange={e => setDraft(d => ({ ...d, tags: e.target.value }))} placeholder="swing, earnings" />
        </label>
        <label>
          Entry plan
          <input value={draft.entry} onChange={e => setDraft(d => ({ ...d, entry: e.target.value }))} placeholder="Entry price / trigger" />
        </label>
        <label>
          Exit plan
          <input value={draft.exit} onChange={e => setDraft(d => ({ ...d, exit: e.target.value }))} placeholder="Target / stop" />
        </label>
        <label>
          Thesis
          <textarea rows={2} value={draft.thesis} onChange={e => setDraft(d => ({ ...d, thesis: e.target.value }))} placeholder="Why this trade?" />
        </label>
        <label>
          Postmortem template
          <textarea rows={2} value={draft.postmortem} onChange={e => setDraft(d => ({ ...d, postmortem: e.target.value }))} placeholder="What worked / failed?" />
        </label>
        <button type="button" className="primary" onClick={addEntry}>Add entry</button>
        <div className="feature-controls">
          <button type="button" className={`ghost${filter === 'all' ? ' primary' : ''}`} onClick={() => setFilter('all')}>All</button>
          {symbol && (
            <button type="button" className={`ghost${filter === symbol ? ' primary' : ''}`} onClick={() => setFilter(symbol)}>
              {symbol.replace(/\.(NSE|BSE)$/, '')}
            </button>
          )}
        </div>
      </div>
      <ul className="reason-list compact">
        {visible.length === 0 && <li className="subtle">No journal entries yet.</li>}
        {visible.map(e => (
          <li key={e.id}>
            <strong>{e.symbol}</strong> · {new Date(e.date).toLocaleDateString('en-IN')}
            {e.tags?.length > 0 && <span className="subtle"> · {e.tags.join(', ')}</span>}
            {e.thesis && <p style={{ margin: '4px 0' }}>{e.thesis}</p>}
            {(e.entry || e.exit) && (
              <p className="subtle">Entry: {e.entry || '—'} · Exit: {e.exit || '—'}</p>
            )}
            {e.postmortem && <p className="subtle">Postmortem: {e.postmortem}</p>}
            <button type="button" className="ghost" onClick={() => deleteEntry(e.id)}>Delete</button>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function ExportCenter({ analysis, genaiResult, holdings = [] }) {
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('')
  const [importKind, setImportKind] = useState('watchlist')
  const notify = loadStore(NOTIFY_KEY, {})

  function briefSections() {
    const dossier = analysis?.dossier || {}
    const tech = analysis?.technicals || {}
    const ratings = analysis?.ratings || {}
    return [
      { heading: 'Verdict', body: dossier.conviction?.plain_english || deriveAction(analysis) },
      {
        heading: 'Key metrics',
        body: [
          `Symbol: ${analysis?.symbol || '—'}`,
          `Price: ${tech.price ?? '—'}`,
          `Composite: ${ratings.composite_score ?? '—'} (${ratings.composite_grade || '—'})`,
          `RSI 14: ${tech.momentum?.rsi_14 ?? '—'}`,
          `ATR 14: ${tech.volatility?.atr_14 ?? '—'}`,
        ],
      },
      {
        heading: 'Flags',
        body: [
          ...((dossier.signal_radar?.green_flags || []).map(g => `Green: ${g}`)),
          ...((dossier.signal_radar?.red_flags || []).map(r => `Red: ${r}`)),
        ].slice(0, 12),
      },
      {
        heading: 'GenAI',
        body: genaiResult?.insight?.executive_summary
          || genaiResult?.insight?.summary
          || 'No GenAI brief yet.',
      },
      {
        heading: 'Disclaimer',
        body: 'Educational research only — not investment advice.',
      },
    ]
  }

  function briefCsvRows() {
    const tech = analysis?.technicals || {}
    const ratings = analysis?.ratings || {}
    return [
      { metric: 'symbol', value: analysis?.symbol, symbol: analysis?.symbol },
      { metric: 'price', value: tech.price, symbol: analysis?.symbol },
      { metric: 'composite_score', value: ratings.composite_score, symbol: analysis?.symbol },
      { metric: 'composite_grade', value: ratings.composite_grade, symbol: analysis?.symbol },
      { metric: 'rsi_14', value: tech.momentum?.rsi_14, symbol: analysis?.symbol },
      { metric: 'atr_14', value: tech.volatility?.atr_14, symbol: analysis?.symbol },
      { metric: 'action', value: deriveAction(analysis), symbol: analysis?.symbol },
    ]
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  function downloadMarkdown() {
    if (!analysis) return
    const md = buildMarkdownBrief(analysis, genaiResult)
    downloadBlob(new Blob([md], { type: 'text/markdown;charset=utf-8' }), `${safeName(analysis.symbol)}_brief.md`)
    setStatus('Markdown downloaded')
  }

  async function exportHtml() {
    if (!analysis) return
    setBusy(true)
    setStatus('')
    try {
      const data = await apiPost('/api/desk/export-html', {
        title: `${analysis.symbol} research brief`,
        sections: briefSections(),
      })
      const html = data.html || ''
      const win = window.open('', '_blank')
      if (win) {
        win.document.write(html)
        win.document.close()
        win.focus()
        win.print()
      }
      setStatus('Print window opened (Save as PDF from print dialog)')
      if (notify.webhook_url) {
        await apiPost('/api/desk/notify', {
          alerts: [{ level: 'export', message: `Exported brief for ${analysis.symbol}` }],
          webhook_url: notify.webhook_url,
        })
      }
    } catch (err) {
      setStatus(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function exportPdf() {
    if (!analysis) return
    setBusy(true)
    setStatus('')
    try {
      const blob = await apiPostBlob('/api/desk/export-pdf', {
        title: `${analysis.symbol} research brief`,
        sections: briefSections(),
      })
      downloadBlob(blob, `${safeName(analysis.symbol)}_brief.pdf`)
      setStatus('PDF downloaded')
    } catch (err) {
      setStatus(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function exportCsv(kind) {
    setBusy(true)
    setStatus('')
    try {
      let rows = []
      if (kind === 'brief') {
        if (!analysis) throw new Error('Analyze a symbol first.')
        rows = briefCsvRows()
      } else if (kind === 'watchlist') {
        rows = loadStore('scanBhavWatchlist', [])
          .map(s => (typeof s === 'string' ? { symbol: s } : s))
      } else if (kind === 'journal') {
        rows = loadStore(RICH_JOURNAL_KEY, [])
      } else if (kind === 'holdings') {
        rows = holdings || []
        if (!rows.length) throw new Error('No paper holdings to export.')
      }
      const data = await apiPost('/api/desk/export-csv', { kind, rows, symbol: analysis?.symbol })
      downloadBlob(
        new Blob([data.csv || ''], { type: 'text/csv;charset=utf-8' }),
        data.filename || `scan_bhav_${kind}.csv`,
      )
      setStatus(`${kind} CSV downloaded (${data.row_count ?? 0} rows)`)
    } catch (err) {
      setStatus(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function importCsvFile(file) {
    if (!file) return
    setBusy(true)
    setStatus('')
    try {
      const csv_text = await file.text()
      const data = await apiPost('/api/desk/import-csv', { kind: importKind, csv_text })

      if (importKind === 'watchlist') {
        const existing = loadStore('scanBhavWatchlist', [])
        const merged = [...new Set([...(existing || []), ...(data.symbols || [])])]
        saveStore('scanBhavWatchlist', merged)
        setStatus(`Imported ${data.count || 0} symbols into watchlist (${merged.length} total)`)
      } else if (importKind === 'journal') {
        const existing = loadStore(RICH_JOURNAL_KEY, [])
        const merged = [...(data.entries || []), ...existing].slice(0, 200)
        saveStore(RICH_JOURNAL_KEY, merged)
        setStatus(`Imported ${data.count || 0} journal entries`)
      } else if (importKind === 'holdings') {
        setStatus(
          `Parsed ${data.count || 0} holdings from CSV. `
          + 'Open Portfolio and Purchase to add paper lots (CSV is a checklist, not auto-buy).',
        )
        if (data.holdings?.length) {
          sessionStorage.setItem('scanBhavHoldingsImport', JSON.stringify(data.holdings))
        }
      }
    } catch (err) {
      setStatus(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function importPdfFile(file) {
    if (!file) return
    setBusy(true)
    setStatus('')
    try {
      const form = new FormData()
      form.append('file', file)
      const data = await apiPostForm('/api/desk/import-pdf', form)
      const existing = loadStore('scanBhavWatchlist', [])
      const merged = [...new Set([...(existing || []), ...(data.symbols || [])])]
      saveStore('scanBhavWatchlist', merged)
      setStatus(
        `PDF scanned — added ${data.symbol_count || 0} symbols to watchlist `
        + `(${merged.length} total). Preview: ${(data.text_preview || '').slice(0, 80)}…`,
      )
    } catch (err) {
      setStatus(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <div><p className="eyebrow">EXPORT / IMPORT</p><h3>PDF · CSV · Markdown</h3></div>
        {analysis?.symbol && <span className="subtle">{analysis.symbol}</span>}
      </div>

      <p className="eyebrow" style={{ marginBottom: 6 }}>Export</p>
      <div className="feature-controls">
        <button type="button" className="primary" disabled={!analysis || busy} onClick={exportPdf}>
          {busy ? 'Working…' : 'Download PDF'}
        </button>
        <button type="button" className="ghost" disabled={!analysis || busy} onClick={exportHtml}>
          HTML / print
        </button>
        <button type="button" className="ghost" disabled={!analysis} onClick={downloadMarkdown}>
          Markdown
        </button>
      </div>
      <div className="feature-controls" style={{ marginTop: 8 }}>
        <button type="button" className="ghost" disabled={!analysis || busy} onClick={() => exportCsv('brief')}>
          Brief CSV
        </button>
        <button type="button" className="ghost" disabled={busy} onClick={() => exportCsv('watchlist')}>
          Watchlist CSV
        </button>
        <button type="button" className="ghost" disabled={busy} onClick={() => exportCsv('journal')}>
          Journal CSV
        </button>
        <button type="button" className="ghost" disabled={busy || !holdings?.length} onClick={() => exportCsv('holdings')}>
          Holdings CSV
        </button>
      </div>

      <p className="eyebrow" style={{ margin: '14px 0 6px' }}>Import</p>
      <div className="buy-grid">
        <label>
          CSV kind
          <select value={importKind} onChange={e => setImportKind(e.target.value)}>
            <option value="watchlist">Watchlist</option>
            <option value="journal">Journal+</option>
            <option value="holdings">Holdings (preview)</option>
          </select>
        </label>
        <label className="ghost" style={{ cursor: 'pointer', alignSelf: 'end' }}>
          Import CSV
          <input
            type="file"
            accept=".csv,text/csv"
            style={{ display: 'none' }}
            onChange={e => importCsvFile(e.target.files?.[0])}
          />
        </label>
        <label className="ghost" style={{ cursor: 'pointer', alignSelf: 'end' }}>
          Import PDF → watchlist
          <input
            type="file"
            accept="application/pdf,.pdf"
            style={{ display: 'none' }}
            onChange={e => importPdfFile(e.target.files?.[0])}
          />
        </label>
      </div>

      {status && <p className="subtle" style={{ marginTop: 10 }}>{status}</p>}
      <p className="subtle">
        PDF downloads a real .pdf file. CSV import merges into local watchlist/journal.
        Holdings CSV is a checklist — paper lots still go through Portfolio Purchase.
      </p>
    </section>
  )
}

function safeName(symbol) {
  return String(symbol || 'brief').replace(/[^a-zA-Z0-9._-]/g, '_')
}

export function MfDiscovery({ onError }) {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setBusy(true)
      onError?.('')
      try {
        const payload = await apiGet('/api/desk/mf-universe')
        if (!cancelled) setData(payload)
      } catch (err) {
        onError?.(err.message)
      } finally {
        if (!cancelled) setBusy(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [onError])

  const funds = data?.funds || data?.items || []
  const byCategory = useMemo(() => {
    const map = new Map()
    for (const f of funds) {
      const cat = f.category || 'Other'
      if (!map.has(cat)) map.set(cat, [])
      map.get(cat).push(f)
    }
    return [...map.entries()]
  }, [funds])

  return (
    <section className="panel">
      <div className="panel-head">
        <div><p className="eyebrow">MUTUAL FUNDS</p><h3>Discovery</h3></div>
        {busy && <span className="subtle">Loading…</span>}
      </div>
      {data?.plain && <p className="subtle">{data.plain}</p>}
      {data?.sip_hint && <p>{data.sip_hint}</p>}
      {byCategory.map(([cat, items]) => (
        <div key={cat} style={{ marginTop: 12 }}>
          <p className="eyebrow">{cat}</p>
          <div className="horizon-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))' }}>
            {items.map(f => (
              <article key={f.id || f.name} className="scenario-card">
                <h4>{f.name}</h4>
                <p className="subtle">{f.risk || f.risk_label || '—'}</p>
                {f.sip_tag && <p>{f.sip_tag}</p>}
                {f.note && <p className="subtle">{f.note}</p>}
              </article>
            ))}
          </div>
        </div>
      ))}
      {funds.length === 0 && !busy && <p className="subtle">No fund list available.</p>}
    </section>
  )
}

export function CurriculumPanel() {
  const [courses, setCourses] = useState([])
  const [busy, setBusy] = useState(false)
  const [completed, setCompleted] = useState(() => loadStore(CURRICULUM_KEY, []))

  useEffect(() => {
    saveStore(CURRICULUM_KEY, completed)
  }, [completed])

  useEffect(() => {
    let cancelled = false
    async function load() {
      setBusy(true)
      try {
        const data = await apiGet('/api/desk/curriculum')
        if (!cancelled) setCourses(data.courses || data.items || [])
      } catch {
        if (!cancelled) setCourses([])
      } finally {
        if (!cancelled) setBusy(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  function toggleLesson(id) {
    setCompleted(prev => (
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    ))
  }

  const totalLessons = courses.reduce((n, c) => n + (c.lessons?.length || 0), 0)

  return (
    <section className="panel">
      <div className="panel-head">
        <div><p className="eyebrow">COURSES</p><h3>Learning path</h3></div>
        <span className="subtle">{completed.length}/{totalLessons || '—'} done</span>
      </div>
      {busy && <p className="subtle">Loading curriculum…</p>}
      {courses.map(course => (
        <div key={course.id || course.title} style={{ marginBottom: 16 }}>
          <h4>{course.title}</h4>
          {course.description && <p className="subtle">{course.description}</p>}
          <ul className="reason-list compact">
            {(course.lessons || []).map(lesson => (
              <li key={lesson.id}>
                <label className="refresh-toggle">
                  <input
                    type="checkbox"
                    checked={completed.includes(lesson.id)}
                    onChange={() => toggleLesson(lesson.id)}
                  />
                  <span>
                    <strong>{lesson.title}</strong>
                    {lesson.minutes != null && <span className="subtle"> · {lesson.minutes} min</span>}
                  </span>
                </label>
                {lesson.body && <p className="subtle" style={{ marginLeft: 24 }}>{lesson.body}</p>}
              </li>
            ))}
          </ul>
        </div>
      ))}
      {courses.length === 0 && !busy && <p className="subtle">Curriculum unavailable.</p>}
    </section>
  )
}

function readLocalBundle() {
  const bundle = {}
  for (const key of ACCOUNT_KEYS) {
    const raw = localStorage.getItem(key)
    if (raw != null) {
      try {
        bundle[key] = JSON.parse(raw)
      } catch {
        bundle[key] = raw
      }
    }
  }
  return bundle
}

function writeLocalBundle(bundle) {
  for (const key of ACCOUNT_KEYS) {
    if (bundle[key] !== undefined) {
      const val = typeof bundle[key] === 'string' ? bundle[key] : JSON.stringify(bundle[key])
      localStorage.setItem(key, val)
    }
  }
}

export function AccountSync() {
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('')

  async function exportBundle() {
    setBusy(true)
    setStatus('')
    try {
      const local = readLocalBundle()
      const data = await apiPost('/api/desk/account/export', local)
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `scan_bhav_sync_${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
      setStatus('Bundle exported')
    } catch (err) {
      setStatus(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function importBundle(file) {
    if (!file) return
    setBusy(true)
    setStatus('')
    try {
      const text = await file.text()
      const parsed = JSON.parse(text)
      const data = await apiPost('/api/desk/account/import', parsed)
      const payload = data.bundle || data.payload || parsed
      writeLocalBundle(payload)
      setStatus('Import complete — reload page to apply all UI state')
    } catch (err) {
      setStatus(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <div><p className="eyebrow">SYNC</p><h3>Account bundle</h3></div>
      </div>
      <p className="subtle">
        Export wizard, watchlist, journals, notify settings, curriculum progress, and beginner flags.
        For PDF/CSV research files use Analyze → Export.
      </p>
      <div className="feature-controls">
        <button type="button" className="primary" disabled={busy} onClick={exportBundle}>
          {busy ? 'Working…' : 'Export JSON'}
        </button>
        <label className="ghost file-ghost">
          Import JSON
          <input
            type="file"
            accept="application/json,.json"
            hidden
            onChange={e => importBundle(e.target.files?.[0])}
          />
        </label>
      </div>
      {status && <p className="subtle">{status}</p>}
    </section>
  )
}

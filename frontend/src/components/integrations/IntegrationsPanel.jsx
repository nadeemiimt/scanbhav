import { useEffect, useState } from 'react'
import { apiGet, apiPost, apiPostStream } from '../../lib/apiClient'
import { useSymbolSearch } from '../../hooks/useSymbolSearch'
import { SymbolSearchField } from '../ui/SymbolSearchField'
import { normalizeAppSymbol } from '../../lib/symbolValidate'

const KEY_IDS = ['alphavantage', 'finnhub', 'openai', 'anthropic', 'cursor']

export function IntegrationsPanel() {
  const [catalog, setCatalog] = useState(null)
  const [keys, setKeys] = useState({})
  const [brokerTokens, setBrokerTokens] = useState({})
  const [drafts, setDrafts] = useState({})
  const [message, setMessage] = useState('')
  const [custom, setCustom] = useState({
    id: 'custom',
    label: 'My data API',
    base_url: '',
    path_template: '/quote?symbol={symbol}',
    header_name: 'Authorization',
    header_prefix: 'Bearer',
    api_key: '',
  })

  async function load() {
    const data = await apiGet('/api/integrations')
    setCatalog(data.catalog)
    setKeys(data.keys || {})
    setBrokerTokens(data.broker_tokens || {})
  }

  useEffect(() => { load().catch(err => setMessage(err.message)) }, [])

  async function saveKey(providerId) {
    setMessage('')
    const res = await apiPost('/api/integrations/key', {
      provider_id: providerId,
      api_key: drafts[providerId] || '',
    })
    setDrafts(prev => ({ ...prev, [providerId]: '' }))
    setKeys(prev => ({ ...prev, [providerId]: res }))
    setMessage(res.configured ? `${providerId} saved.` : `${providerId} cleared.`)
  }

  async function clearKey(providerId) {
    setMessage('')
    const res = await apiPost('/api/integrations/key/clear', {
      provider_id: providerId,
      api_key: '',
    })
    setDrafts(prev => ({ ...prev, [providerId]: '' }))
    setKeys(prev => {
      const next = { ...prev }
      delete next[providerId]
      return next
    })
    setMessage(`${providerId} cleared.`)
    return res
  }

  async function clearBrokerToken(broker) {
    setMessage('')
    await apiPost('/api/integrations/broker-token/clear', { provider_id: broker, api_key: '' })
    setBrokerTokens(prev => ({ ...prev, [broker]: {} }))
    setMessage(`${broker} access token cleared. App key/secret unchanged.`)
  }

  async function testKey(providerId) {
    setMessage('')
    const res = await apiPost('/api/integrations/test', { provider_id: providerId, symbol: 'RELIANCE.NSE' })
    setMessage(res.ok ? `${providerId} works. Price ${res.price}.` : (res.reason || 'Test failed.'))
  }

  async function saveCustom() {
    setMessage('')
    await apiPost('/api/integrations/connector', custom)
    setMessage('Custom API saved.')
    setCustom(prev => ({ ...prev, api_key: '' }))
  }

  const guide = catalog?.runtime_guide
  const keyed = catalog?.keyed || []
  const brokerKeys = catalog?.broker_app_keys || []

  return (
    <section className="settings-section">
      <h4>What you need to run</h4>
      {guide ? (
        <div className="token-guide">
          <p className="settings-hint"><strong>{guide.headline}</strong></p>
          <p className="subtle">{guide.how_to_manage}</p>
          {(guide.required || []).map(row => (
            <p key={row.id} className="subtle">Required: {row.label} — {row.plain}</p>
          ))}
          {(guide.recommended || []).length > 0 && (
            <div className="token-guide-block">
              <p className="eyebrow">Recommended</p>
              <ul className="subtle">
                {guide.recommended.map(row => (
                  <li key={row.id}><b>{row.label}</b> — {row.plain}</li>
                ))}
              </ul>
            </div>
          )}
          {(guide.optional || []).length > 0 && (
            <div className="token-guide-block">
              <p className="eyebrow">Optional</p>
              <ul className="subtle">
                {guide.optional.map(row => (
                  <li key={row.id}><b>{row.label}</b> — {row.plain}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : (
        <p className="subtle settings-hint">
          Yahoo and NSE work with no key. Add a key only for the extra source you want.
        </p>
      )}

      <h4>Your API keys</h4>
      <p className="subtle settings-hint">
        Keys stay on this computer and are shown back only as a hint (••••last4). Clear removes them from the local secrets file.
      </p>
      {KEY_IDS.map(id => {
        const meta = keyed.find(row => row.id === id)
        const saved = keys[id]
        return (
          <label key={id} className="settings-field">
            {meta?.label || id}
            <span className="subtle"> {saved?.configured ? `saved ${saved.hint}` : 'not set'}</span>
            <input
              type="password"
              autoComplete="off"
              placeholder={meta?.plain || 'Paste key'}
              value={drafts[id] || ''}
              onChange={e => setDrafts(prev => ({ ...prev, [id]: e.target.value }))}
            />
            <span style={{ display: 'flex', gap: 8, marginTop: 6, flexWrap: 'wrap' }}>
              <button type="button" className="ghost" onClick={() => saveKey(id)}>Save</button>
              {saved?.configured && (
                <button type="button" className="ghost" onClick={() => clearKey(id)}>Clear</button>
              )}
              {(id === 'alphavantage' || id === 'finnhub') && (
                <button type="button" className="ghost" onClick={() => testKey(id)}>Test</button>
              )}
              {meta?.docs && (
                <a className="subtle" href={meta.docs} target="_blank" rel="noreferrer">Get key</a>
              )}
            </span>
          </label>
        )
      })}

      <h4>Broker app keys (live only)</h4>
      <p className="subtle settings-hint">
        Paper Autopilot never needs these. For live ticks / live orders, save the app key and secret here, then complete OAuth from Accounts.
      </p>
      {brokerKeys.map(row => {
        const saved = keys[row.id]
        return (
          <label key={row.id} className="settings-field">
            {row.label}
            <span className="subtle"> {saved?.configured ? `saved ${saved.hint}` : 'not set'}</span>
            <input
              type="password"
              autoComplete="off"
              placeholder={row.plain || 'Paste value'}
              value={drafts[row.id] || ''}
              onChange={e => setDrafts(prev => ({ ...prev, [row.id]: e.target.value }))}
            />
            <span style={{ display: 'flex', gap: 8, marginTop: 6, flexWrap: 'wrap' }}>
              <button type="button" className="ghost" onClick={() => saveKey(row.id)}>Save</button>
              {saved?.configured && (
                <button type="button" className="ghost" onClick={() => clearKey(row.id)}>Clear</button>
              )}
              {row.docs && (
                <a className="subtle" href={row.docs} target="_blank" rel="noreferrer">Docs</a>
              )}
            </span>
          </label>
        )
      })}

      <h4>Broker access tokens</h4>
      <p className="subtle settings-hint">
        Daily OAuth tokens land here after you connect. Clear if login fails or you switched accounts.
      </p>
      {['zerodha', 'groww', 'fyers'].map(broker => {
        const meta = brokerTokens[broker] || {}
        return (
          <div key={broker} className="settings-field" style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <span style={{ textTransform: 'capitalize' }}>{broker}</span>
            <span className="subtle">
              {meta.has_token
                ? `connected${meta.updated_at ? ` · ${String(meta.updated_at).slice(0, 16)}` : ''}`
                : 'no access token'}
            </span>
            {meta.has_token && (
              <button type="button" className="ghost" onClick={() => clearBrokerToken(broker)}>Clear token</button>
            )}
          </div>
        )
      })}

      <h4>Custom data API</h4>
      <label className="settings-field">
        Base URL
        <input value={custom.base_url} onChange={e => setCustom(prev => ({ ...prev, base_url: e.target.value }))} placeholder="https://api.example.com" />
      </label>
      <label className="settings-field">
        Path ({'{symbol}'} is replaced)
        <input value={custom.path_template} onChange={e => setCustom(prev => ({ ...prev, path_template: e.target.value }))} />
      </label>
      <label className="settings-field">
        Custom API key
        <input type="password" autoComplete="off" value={custom.api_key} onChange={e => setCustom(prev => ({ ...prev, api_key: e.target.value }))} />
      </label>
      <button type="button" className="ghost" onClick={saveCustom}>Save custom API</button>
      {message && <p className="subtle">{message}</p>}
      {catalog?.suggested_later && (
        <p className="subtle">Later, if you want deeper history: {catalog.suggested_later.join(' ')}</p>
      )}
    </section>
  )
}

export function SimpleBacktestPanel() {
  const [mode, setMode] = useState('walk_forward')
  const [selected, setSelected] = useState(['RELIANCE.NSE', 'TCS.NSE'])
  const [start, setStart] = useState('2022-01-01')
  const [end, setEnd] = useState('2026-09-01')
  const [randomCount, setRandomCount] = useState(6)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [allowEdits, setAllowEdits] = useState(false)
  const [note, setNote] = useState('')
  const [progress, setProgress] = useState(0)
  const [progressMsg, setProgressMsg] = useState('')
  const [progressLog, setProgressLog] = useState([])
  const stockSearch = useSymbolSearch('')

  async function addStock(raw) {
    setNote('')
    const resolved = raw
      ? (() => {
          try {
            return normalizeAppSymbol(raw)
          } catch {
            return null
          }
        })()
      : await stockSearch.resolveSymbol()
    if (!resolved) {
      setNote('Pick a stock from the search list (e.g. type Reliance → RELIANCE.NSE).')
      return
    }
    setSelected(prev => (prev.includes(resolved) ? prev : [...prev, resolved].slice(0, 25)))
    stockSearch.setQuery('')
    stockSearch.clearSuggestions()
  }

  function removeStock(sym) {
    setSelected(prev => prev.filter(item => item !== sym))
  }

  async function run() {
    if (mode !== 'random' && selected.length === 0) {
      setNote('Add at least one stock from the search dropdown, or switch to Random Nifty names.')
      return
    }
    setBusy(true)
    setNote('')
    setResult(null)
    setProgress(1)
    setProgressMsg('Starting backtest…')
    setProgressLog([])
    try {
      const response = await apiPostStream('/api/backtest/simple/stream', {
        mode,
        symbols: selected,
        start: start || null,
        end: end || null,
        random_count: Number(randomCount) || 6,
      })
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let gotDone = false
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const chunks = buffer.split('\n\n')
        buffer = chunks.pop() || ''
        for (const chunk of chunks) {
          const line = chunk.split('\n').find(l => l.startsWith('data: '))
          if (!line) continue
          let event
          try {
            event = JSON.parse(line.slice(6))
          } catch {
            continue
          }
          if (event.progress != null) setProgress(Math.max(0, Math.min(100, Number(event.progress) || 0)))
          if (event.message) setProgressMsg(event.message)
          if (event.type === 'symbol_done' || event.type === 'symbol_start') {
            setProgressLog(prev => [...prev.slice(-8), event.message || event.symbol].filter(Boolean))
          }
          if (event.type === 'error') {
            setNote(event.message || 'Backtest failed.')
          }
          if (event.type === 'done' && event.result) {
            gotDone = true
            setResult(event.result)
            setProgress(100)
            setProgressMsg('Backtest complete.')
          }
        }
      }
      if (!gotDone) setNote('Backtest ended without a result. Try again.')
    } catch (err) {
      setNote(err.message)
      setProgressMsg('')
    } finally {
      setBusy(false)
    }
  }

  async function explain(gapId) {
    setNote('Asking the model…')
    const data = await apiPost('/api/learning/explain', { gap_id: gapId })
    setNote(data.note || data.reason || 'No note.')
  }

  async function cursorLearn(gapId) {
    setNote('Cursor is reading the gap. This can take a few minutes.')
    const data = await apiPost('/api/learning/cursor', { gap_id: gapId, allow_code_edits: allowEdits })
    setNote(data.summary || data.reason || data.status || 'Done.')
  }

  return (
    <section className="panel" id="simple-backtest">
      <div className="panel-head">
        <div>
          <p className="eyebrow">BACKTEST · MULTI-DATE</p>
          <h3>Check a rule on past prices</h3>
        </div>
        <button type="button" className="primary" disabled={busy} onClick={run}>
          {busy ? `Running ${progress}%` : 'Run check'}
        </button>
      </div>
      <p className="subtle">
        For several dates: set <b>Start</b> and <b>End</b>, choose <b>Exact date range</b>, add stocks from search, then Run check.
        Walk-forward (default) uses your date window but only scores the later part, so the rule cannot cheat on history.
        Random picks Nifty names inside the same date window.
      </p>
      <label className="settings-field">
        How to choose history
        <select value={mode} onChange={e => setMode(e.target.value)} disabled={busy}>
          <option value="walk_forward">Later dates only (recommended)</option>
          <option value="date_range">Exact date range (all days in Start→End)</option>
          <option value="symbols">These stocks (with Start→End if set)</option>
          <option value="random">Random Nifty names (with Start→End if set)</option>
        </select>
      </label>
      {mode !== 'random' && (
        <div className="settings-field backtest-stock-picker">
          <span>Stocks</span>
          <SymbolSearchField
            inputId="backtest-symbol-search"
            value={stockSearch.query}
            onChange={stockSearch.onQueryChange}
            onPick={addStock}
            searching={stockSearch.searching}
            suggestions={stockSearch.suggestions}
            placeholder="Search name or code — e.g. Reliance, TCS, INFY"
          />
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
            {selected.map(sym => (
              <button
                key={sym}
                type="button"
                className="ghost"
                disabled={busy}
                onClick={() => removeStock(sym)}
                title="Remove"
              >
                {sym} ×
              </button>
            ))}
            {selected.length === 0 && (
              <span className="subtle">No stocks yet — type a name and pick from the list.</span>
            )}
          </div>
        </div>
      )}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <label className="settings-field">Start date <input type="date" value={start} disabled={busy} onChange={e => setStart(e.target.value)} /></label>
        <label className="settings-field">End date <input type="date" value={end} disabled={busy} onChange={e => setEnd(e.target.value)} /></label>
        {mode === 'random' && (
          <label className="settings-field">Random count <input type="number" min={1} max={25} value={randomCount} disabled={busy} onChange={e => setRandomCount(e.target.value)} /></label>
        )}
      </div>
      {(busy || progress > 0) && (
        <div className="backtest-progress" aria-live="polite">
          <div className="backtest-progress-head">
            <span>{busy ? 'In progress' : (progress >= 100 ? 'Finished' : 'Stopped')}</span>
            <strong>{Math.round(progress)}%</strong>
          </div>
          <div className="backtest-progress-track" role="progressbar" aria-valuenow={Math.round(progress)} aria-valuemin={0} aria-valuemax={100}>
            <div className="backtest-progress-fill" style={{ width: `${Math.max(progress, busy ? 3 : 0)}%` }} />
          </div>
          {progressMsg && <p className="subtle backtest-progress-msg">{progressMsg}</p>}
          {progressLog.length > 0 && (
            <ul className="subtle backtest-progress-log">
              {progressLog.map((line, i) => <li key={`${i}-${line.slice(0, 24)}`}>{line}</li>)}
            </ul>
          )}
        </div>
      )}
      {result && (
        <div style={{ marginTop: 10 }}>
          <p>{result.headline}</p>
          {result.summary && (
            <p className="subtle">
              Scored {result.summary.scored || 0} · skipped {result.summary.skipped || 0}
              {result.summary.remapped ? ` · remapped ${result.summary.remapped} ticker(s)` : ''}
              {result.average_expectancy_pct != null ? ` · avg expectancy ${result.average_expectancy_pct}%` : ''}
            </p>
          )}
          <ul className="subtle">
            {(result.results || []).map((row, idx) => (
              <li key={`${row.symbol}-${idx}`} className={row.skipped ? 'down' : undefined}>
                {row.skipped
                  ? (row.reason || `${row.symbol}: could not score`)
                  : (row.plain || `${row.symbol}: done`)}
              </li>
            ))}
            {!(result.results || []).length && (result.plain || []).map(line => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          {(result.gaps || []).map(gap => (
            <div key={gap.id} className="subtle" style={{ marginTop: 8 }}>
              <p>Lesson: {gap.summary}</p>
              <button type="button" className="ghost" onClick={() => explain(gap.id)}>Ask AI what to change</button>
              <button type="button" className="ghost" onClick={() => cursorLearn(gap.id)}>Ask Cursor to apply it</button>
            </div>
          ))}
          <label className="refresh-toggle">
            <input type="checkbox" checked={allowEdits} onChange={e => setAllowEdits(e.target.checked)} />
            Allow Cursor to edit recommendation code (not orders)
          </label>
        </div>
      )}
      {note && <p className="subtle">{note}</p>}
    </section>
  )
}

import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiPost } from '../../lib/apiClient'
import useConfirmDialog from '../../hooks/useConfirmDialog'

const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
const number = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 })

const BROKER_LABELS = {
  zerodha: 'Zerodha',
  groww: 'Groww',
  fyers: 'FYERS',
}

export function BrokerAccountsPage({ onError }) {
  const { confirm, dialog } = useConfirmDialog()
  const [busy, setBusy] = useState(false)
  const [holdings, setHoldings] = useState(null)
  const [payout, setPayout] = useState(null)
  const [preview, setPreview] = useState(null)
  const [executeResult, setExecuteResult] = useState(null)
  const [taxBracket, setTaxBracket] = useState(30)
  const [form, setForm] = useState({
    account_holder: '',
    bank_name: '',
    account_number: '',
    ifsc: '',
    upi_id: '',
  })

  const loadAll = useCallback(async () => {
    setBusy(true)
    onError('')
    try {
      const [h, p] = await Promise.all([
        apiGet('/api/broker/holdings/consolidated'),
        apiGet('/api/broker/payout-account'),
      ])
      setHoldings(h)
      setPayout(p)
      if (p?.account) {
        setForm(prev => ({
          ...prev,
          account_holder: p.account.account_holder || prev.account_holder,
          bank_name: p.account.bank_name || prev.bank_name,
          ifsc: p.account.ifsc || prev.ifsc,
          upi_id: p.account.upi_id || prev.upi_id,
        }))
      }
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }, [onError])

  useEffect(() => { loadAll() }, [loadAll])

  async function savePayout(e) {
    e.preventDefault()
    setBusy(true)
    onError('')
    try {
      const result = await apiPost('/api/broker/payout-account', form)
      setPayout({ configured: true, account: result.account })
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function runPreview() {
    setBusy(true)
    setPreview(null)
    setExecuteResult(null)
    onError('')
    try {
      const result = await apiPost('/api/broker/sell-all/preview', {
        tax_bracket_rate_pct: Number(taxBracket),
        include_mf: false,
      })
      setPreview(result)
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function runExecute(dryRun = false) {
    const ok = await confirm({
      title: dryRun ? 'Dry-run sell-all' : 'Live sell-all',
      message: dryRun
        ? 'Simulate sell-all on connected brokers without placing orders?'
        : 'Place LIVE market sell orders for all delivery stocks? This cannot be undone from this app.',
      confirmLabel: dryRun ? 'Run dry-run' : 'Place live sells',
      cancelLabel: 'Cancel',
      variant: dryRun ? 'default' : 'danger',
    })
    if (!ok) return
    setBusy(true)
    onError('')
    try {
      const result = await apiPost('/api/broker/sell-all/execute', {
        confirm: !dryRun,
        dry_run: dryRun,
        include_mf: false,
        tax_bracket_rate_pct: Number(taxBracket),
      })
      setExecuteResult(result)
      if (!dryRun) await loadAll()
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const totals = holdings?.totals || {}
  const rows = holdings?.holdings || []
  const byBroker = holdings?.by_broker || {}
  const previewTotals = preview?.totals || {}

  return (
    <div className="broker-accounts-desk">
      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="eyebrow">BROKER ACCOUNTS</p>
            <h2>Zerodha · Groww · FYERS — holdings & sell all</h2>
          </div>
          <button type="button" className="ghost" disabled={busy} onClick={loadAll}>
            {busy ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
        <p className="subtle">
          Pulls live holdings when broker APIs are connected. Research charts still use Yahoo/NSE.
          Connect brokers via Settings / OAuth, then refresh here.
        </p>
        {(holdings?.errors || []).length > 0 && (
          <ul className="reason-list compact broker-errors">
            {holdings.errors.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        )}
        <div className="hero-stats portfolio-stats">
          <article className="hero-stat"><p>Positions</p><strong>{totals.positions ?? 0}</strong></article>
          <article className="hero-stat"><p>Invested</p><strong>{money.format(totals.invested || 0)}</strong></article>
          <article className="hero-stat"><p>Market value</p><strong>{money.format(totals.market_value || 0)}</strong></article>
          <article className="hero-stat">
            <p>P&amp;L</p>
            <strong className={(totals.unrealized_pnl || 0) >= 0 ? 'up' : 'down'}>
              {money.format(totals.unrealized_pnl || 0)}
            </strong>
          </article>
        </div>
        <div className="broker-count-pills">
          {Object.entries(BROKER_LABELS).map(([id, label]) => (
            <span key={id} className="ghost desk-tool-chip">
              {label}: {byBroker[id]?.length ?? holdings?.brokers?.[id] ?? 0}
            </span>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <div><p className="eyebrow">HOLDINGS</p><h3>Stocks &amp; mutual funds</h3></div>
        </div>
        {rows.length === 0 && (
          <p className="subtle">
            No live holdings yet. Connect Zerodha/Groww/FYERS (see Swing desk broker status or OAuth URLs in API docs).
          </p>
        )}
        {rows.length > 0 && (
          <div className="broker-holdings-table-wrap">
            <table className="broker-holdings-table">
              <thead>
                <tr>
                  <th>Broker</th>
                  <th>Symbol</th>
                  <th>Type</th>
                  <th>Qty</th>
                  <th>Avg</th>
                  <th>LTP</th>
                  <th>Value</th>
                  <th>P&amp;L</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(row => (
                  <tr key={row.id}>
                    <td>{BROKER_LABELS[row.broker] || row.broker}</td>
                    <td><b>{row.symbol}</b><br /><span className="subtle">{row.name}</span></td>
                    <td>{row.asset_type === 'mutual_fund' ? 'MF' : 'Stock'}</td>
                    <td>{number.format(row.quantity)}</td>
                    <td>{money.format(row.avg_price)}</td>
                    <td>{money.format(row.last_price)}</td>
                    <td>{money.format(row.market_value)}</td>
                    <td className={(row.pnl || 0) >= 0 ? 'up' : 'down'}>
                      {money.format(row.pnl || 0)}
                      {row.pnl_pct != null && <span className="subtle"> ({number.format(row.pnl_pct)}%)</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="broker-accounts-grid">
        <section className="panel">
          <div className="panel-head">
            <div><p className="eyebrow">PAYOUT ACCOUNT</p><h3>Where proceeds go</h3></div>
          </div>
          <form className="desk-tool-form" onSubmit={savePayout}>
            <label>
              Account holder
              <input value={form.account_holder} onChange={e => setForm(f => ({ ...f, account_holder: e.target.value }))} required />
            </label>
            <label>
              Bank name
              <input value={form.bank_name} onChange={e => setForm(f => ({ ...f, bank_name: e.target.value }))} required />
            </label>
            <label>
              Account number
              <input value={form.account_number} onChange={e => setForm(f => ({ ...f, account_number: e.target.value }))} required />
            </label>
            <label>
              IFSC
              <input value={form.ifsc} onChange={e => setForm(f => ({ ...f, ifsc: e.target.value.toUpperCase() }))} required />
            </label>
            <label>
              UPI ID (optional)
              <input value={form.upi_id} onChange={e => setForm(f => ({ ...f, upi_id: e.target.value }))} placeholder="name@bank" />
            </label>
            <button type="submit" className="primary" disabled={busy}>Save account</button>
          </form>
          {payout?.configured && (
            <p className="subtle swing-save-msg">
              Saved: {payout.account?.account_holder} · {payout.account?.bank_name} ·{' '}
              {payout.account?.account_number_masked || '****'}
            </p>
          )}
        </section>

        <section className="panel">
          <div className="panel-head">
            <div><p className="eyebrow">SELL ALL</p><h3>Exit &amp; transfer estimate</h3></div>
          </div>
          <label>
            Tax slab % (debt MF / reference)
            <input type="number" min="0" max="42" value={taxBracket} onChange={e => setTaxBracket(e.target.value)} />
          </label>
          <div className="feature-controls">
            <button type="button" className="primary" disabled={busy || rows.length === 0} onClick={runPreview}>
              Preview sell all
            </button>
            <button type="button" className="ghost" disabled={busy} onClick={() => runExecute(true)}>
              Dry run
            </button>
            <button
              type="button"
              className="ghost"
              disabled={busy || !payout?.configured || rows.length === 0}
              onClick={() => runExecute(false)}
            >
              Sell all (live)
            </button>
          </div>
          {!payout?.configured && (
            <p className="subtle">Save payout account before live sell-all.</p>
          )}
          {preview && (
            <div className="broker-sell-preview">
              <p className="eyebrow">PREVIEW</p>
              <div className="hero-stats portfolio-stats">
                <article className="hero-stat"><p>Gross</p><strong>{money.format(previewTotals.market_value || 0)}</strong></article>
                <article className="hero-stat"><p>Fees</p><strong>{money.format(previewTotals.sell_fees || 0)}</strong></article>
                <article className="hero-stat"><p>Tax est.</p><strong>{money.format(previewTotals.tax_estimate || 0)}</strong></article>
                <article className="hero-stat"><p>Net transfer</p><strong>{money.format(previewTotals.net_transfer_estimate || 0)}</strong></article>
                <article className="hero-stat"><p>After tax est.</p><strong>{money.format(previewTotals.net_after_tax_estimate || 0)}</strong></article>
              </div>
              <p className="subtle">{preview.disclaimer}</p>
            </div>
          )}
          {executeResult && (
            <div className="broker-sell-result">
              <p className="eyebrow">EXECUTION</p>
              <p>{executeResult.message}</p>
              {(executeResult.orders || []).length > 0 && (
                <ul className="reason-list compact">
                  {executeResult.orders.slice(0, 12).map((o, i) => (
                    <li key={i}>{o.symbol || o.order_id} — {o.status || o.message || 'queued'}</li>
                  ))}
                </ul>
              )}
              {(executeResult.errors || []).length > 0 && (
                <ul className="reason-list compact broker-errors">
                  {executeResult.errors.map((e, i) => <li key={i}>{e}</li>)}
                </ul>
              )}
            </div>
          )}
        </section>
      </div>
      {dialog}
    </div>
  )
}

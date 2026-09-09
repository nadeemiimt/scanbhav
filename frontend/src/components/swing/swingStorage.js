import { loadStore, saveStore } from '../../lib/storage'

export const SWING_TRADES_KEY = 'scanBhavSwingTrades'
export const SWING_WATCHLIST_KEY = 'scanBhavSwingWatchlist'
export const SWING_ALERTS_KEY = 'scanBhavSwingAlerts'
export const SWING_BROKER_KEY = 'scanBhavSwingBroker'

export const DEFAULT_BROKER = {
  broker: 'stub',
  product: 'cnc',
  order_type: 'limit',
  auto_buy_on_active: true,
}

export function loadBrokerPrefs() {
  return { ...DEFAULT_BROKER, ...loadStore(SWING_BROKER_KEY, {}) }
}

export function saveBrokerPrefs(prefs) {
  saveStore(SWING_BROKER_KEY, prefs)
}

export function loadSwingAlerts() {
  return loadStore(SWING_ALERTS_KEY, [])
}

export function saveSwingAlerts(alerts) {
  saveStore(SWING_ALERTS_KEY, alerts)
}

export function exportSwingBook(trades) {
  const blob = new Blob([JSON.stringify({ exported_at: new Date().toISOString(), trades }, null, 2)], {
    type: 'application/json',
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `swing-book-${new Date().toISOString().slice(0, 10)}.json`
  a.click()
  URL.revokeObjectURL(url)
}

export function exportSwingBookCsv(trades) {
  const header = ['symbol', 'status', 'horizon', 'entry', 'stop', 'shares', 'targets', 'reward_r', 'thesis', 'created_at', 'closed_at']
  const rows = trades.map(t => [
    t.symbol,
    t.status,
    t.horizon,
    t.entry,
    t.stop,
    t.shares,
    (t.targets || []).join('|'),
    t.reward_r ?? '',
    (t.thesis || '').replace(/"/g, '""'),
    t.created_at || '',
    t.closed_at || '',
  ])
  const csv = [header.join(','), ...rows.map(r => r.map(c => `"${c}"`).join(','))].join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `swing-book-${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

export function daysHeld(trade) {
  const start = trade.activated_at || trade.created_at
  if (!start) return null
  const ms = Date.now() - new Date(start).getTime()
  return Math.max(0, Math.floor(ms / 86400000))
}

export function isDuplicatePlan(trades, symbol, entry, excludeId) {
  const sym = (symbol || '').toUpperCase()
  const e = Number(entry)
  return trades.some(t => (
    t.id !== excludeId
    && t.symbol === sym
    && t.status !== 'closed'
    && Math.abs(Number(t.entry) - e) < 0.05
  ))
}

export function appendJournalEntry(trade, note) {
  const key = 'scanBhavRichJournal'
  const entries = loadStore(key, [])
  entries.unshift({
    id: `${Date.now()}`,
    symbol: trade.symbol,
    side: trade.status === 'closed' ? 'exit' : 'swing',
    note: note || trade.thesis || 'Swing trade',
    tags: ['swing', trade.horizon],
    pnl: trade.unrealized_pnl,
    at: new Date().toISOString(),
  })
  saveStore(key, entries.slice(0, 500))
}

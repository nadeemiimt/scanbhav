const APP_SYMBOL = /^[A-Z0-9][A-Z0-9&.-]{0,22}\.(NSE|BSE)$/
const BARE_TICKER = /^[A-Z0-9][A-Z0-9&.-]{0,22}$/

export function normalizeAppSymbol(symbol, defaultExchange = 'NSE') {
  let raw = (symbol || '').trim().toUpperCase()
  if (!raw) throw new Error('Symbol is empty.')
  if (raw.endsWith('.NS')) raw = `${raw.slice(0, -3)}.NSE`
  else if (raw.endsWith('.BO')) raw = `${raw.slice(0, -3)}.BSE`
  else if (!/\.(NSE|BSE)$/.test(raw)) {
    if (!BARE_TICKER.test(raw)) throw new Error(`Invalid symbol: ${symbol}`)
    const ex = defaultExchange.toUpperCase() === 'BSE' ? 'BSE' : 'NSE'
    raw = `${raw}.${ex}`
  }
  if (!APP_SYMBOL.test(raw)) throw new Error(`Invalid symbol format: ${symbol}`)
  return raw
}

export function isValidAppSymbol(symbol) {
  try {
    normalizeAppSymbol(symbol)
    return true
  } catch {
    return false
  }
}

export const CURATED_SYMBOLS_MAX = 20

export function normalizeSymbolList(symbols, { maxCount = CURATED_SYMBOLS_MAX, minCount = 0 } = {}) {
  const out = []
  const seen = new Set()
  for (const item of symbols || []) {
    if (!item || !String(item).trim()) continue
    const norm = normalizeAppSymbol(String(item))
    if (seen.has(norm)) continue
    seen.add(norm)
    out.push(norm)
  }
  if (out.length < minCount) throw new Error(`Select at least ${minCount} stock(s).`)
  if (out.length > maxCount) throw new Error(`Maximum ${maxCount} stocks allowed.`)
  return out
}

/** Shared analysis display helpers. */
export const number = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 })
export const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })

export function pretty(value) {
  return String(value || '').replaceAll('_', ' ')
}

export function tipFor(guide, key) {
  const g = guide?.[key]
  if (!g) return null
  return `${g.what}\n\nWhy useful: ${g.why}`
}

export function accuracyCopy(item) {
  const label = item?.accuracy?.label
  if (item?.status === 'rated') {
    return { text: label === 'working' ? 'On track' : label === 'missing' ? 'Missed' : label === 'flat' ? 'Sideways' : 'Rated', cls: label || 'pending' }
  }
  if (!label) return { text: 'Not refreshed', cls: 'pending' }
  if (label === 'working') return { text: 'On track', cls: 'working' }
  if (label === 'missing') return { text: 'Off track', cls: 'missing' }
  if (label === 'flat') return { text: 'Sideways', cls: 'flat' }
  return { text: pretty(label), cls: label }
}

export function expectedMove(stance) {
  const st = String(stance || '').toLowerCase()
  if (['bullish', 'constructive', 'strong_favorable', 'favorable'].includes(st)) return 'Expect ↑'
  if (['bearish', 'cautious', 'unfavorable', 'strong_unfavorable'].includes(st)) return 'Expect ↓'
  return 'Expect quiet'
}


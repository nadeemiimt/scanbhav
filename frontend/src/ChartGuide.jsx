import { useState } from 'react'

const number = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 })

function fmt(v) {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return number.format(Number(v))
}

function pctDist(close, level) {
  if (close == null || level == null || !Number.isFinite(Number(close)) || !Number.isFinite(Number(level)) || level === 0) {
    return null
  }
  return ((Number(close) / Number(level) - 1) * 100)
}

function guideEntry(guide, key) {
  return guide?.[key] || null
}

function guideBlurb(guide, key) {
  const g = guideEntry(guide, key)
  if (!g) return null
  return g.what
}

function guideWhy(guide, key) {
  const g = guideEntry(guide, key)
  if (!g) return null
  return g.why
}

function DefaultChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tip chart-tip-default">
      <p className="chart-tip-date">{label}</p>
      {payload.map(entry => (
        <p key={entry.name || entry.dataKey} className="chart-tip-row">
          <span>{entry.name || entry.dataKey}</span>
          <strong>{fmt(entry.value)}</strong>
        </p>
      ))}
    </div>
  )
}

function CandleGuideBody({ row, label, guide, showVwap, showLevels, showPrior, session, levels }) {
  const { open, high, low, close } = row
  const up = Number(close) >= Number(open)
  const body = Math.abs(Number(close) - Number(open))
  const range = Number(high) - Number(low)
  const upperWick = Number(high) - Math.max(Number(open), Number(close))
  const lowerWick = Math.min(Number(open), Number(close)) - Number(low)

  const overlays = []
  if (row.sma_20 != null) {
    const d = pctDist(close, row.sma_20)
    overlays.push({
      key: 'sma_20',
      label: 'SMA 20',
      value: row.sma_20,
      note: d != null ? `${d >= 0 ? '+' : ''}${fmt(d)}% vs close` : null,
    })
  }
  if (row.sma_50 != null) {
    const d = pctDist(close, row.sma_50)
    overlays.push({
      key: 'sma_50',
      label: 'SMA 50',
      value: row.sma_50,
      note: d != null ? `${d >= 0 ? '+' : ''}${fmt(d)}% vs close` : null,
    })
  }
  if (showVwap && row.vwap != null) {
    const d = pctDist(close, row.vwap)
    overlays.push({
      key: 'vwap',
      label: 'VWAP',
      value: row.vwap,
      note: d != null ? `${d >= 0 ? '+' : ''}${fmt(d)}% vs close` : null,
    })
  }

  return (
    <div className="chart-guide-tip">
      <p className="chart-guide-kicker">Candle · {label}</p>
      <p className="chart-guide-lede">
        {up ? 'Green body' : 'Red body'} — close {up ? '≥' : '<'} open.
        {' '}
        {guideBlurb(guide, 'candlestick') || 'Each bar is one session of trading.'}
      </p>
      <dl className="chart-guide-dl">
        <div>
          <dt>Open</dt>
          <dd>{fmt(open)} — where the session started.</dd>
        </div>
        <div>
          <dt>High</dt>
          <dd>
            {fmt(high)} — peak price;
            {upperWick > 0 && range > 0
              ? ` upper wick ${fmt((upperWick / range) * 100)}% of range (sellers pushed back).`
              : ' no upper wick.'}
          </dd>
        </div>
        <div>
          <dt>Low</dt>
          <dd>
            {fmt(low)} — session low;
            {lowerWick > 0 && range > 0
              ? ` lower wick ${fmt((lowerWick / range) * 100)}% of range (buyers defended).`
              : ' no lower wick.'}
          </dd>
        </div>
        <div>
          <dt>Close</dt>
          <dd>
            {fmt(close)} — final price; body size {fmt(body)} ({range > 0 ? fmt((body / range) * 100) : '—'}% of range).
          </dd>
        </div>
      </dl>
      {overlays.length > 0 && (
        <div className="chart-guide-block">
          <p className="chart-guide-sub">Lines on this bar</p>
          {overlays.map(o => (
            <div key={o.key} className="chart-guide-line-item">
              <strong>{o.label}</strong> {fmt(o.value)}
              {o.note && <span className="subtle"> · {o.note}</span>}
              {guideWhy(guide, o.key) && <p className="chart-guide-why">{guideWhy(guide, o.key)}</p>}
            </div>
          ))}
        </div>
      )}
      {(showLevels || showPrior) && (
        <div className="chart-guide-block">
          <p className="chart-guide-sub">Dashed horizontals (when toggled on)</p>
          {showLevels && levels?.pivot != null && (
            <p className="chart-guide-why">
              <strong>Pivot / R1 / S1</strong> — {guideBlurb(guide, 'pivot') || 'Classic support/resistance from the prior session.'}
            </p>
          )}
          {showPrior && session?.prior_high != null && (
            <p className="chart-guide-why">
              <strong>Prior day H/L</strong> — yesterday&apos;s range; breaks can signal continuation or reversal.
            </p>
          )}
          {showPrior && session?.poc != null && (
            <p className="chart-guide-why">
              <strong>POC</strong> — {guideBlurb(guide, 'poc') || 'Price level with the most volume in the chart window.'}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function RsiGuideBody({ row, label, guide }) {
  const rsi = row?.rsi_14
  const zone = rsi == null ? 'unknown' : rsi >= 70 ? 'overbought' : rsi <= 30 ? 'oversold' : 'neutral'
  const zoneText = {
    overbought: 'Above 70 — momentum stretched; trend can continue but pullbacks are common.',
    oversold: 'Below 30 — selling stretched; bounces possible but downtrends can stay oversold.',
    neutral: 'Between 30–70 — no extreme; trend continuation often looks healthier here.',
    unknown: 'RSI not available for this bar yet.',
  }[zone]

  return (
    <div className="chart-guide-tip">
      <p className="chart-guide-kicker">RSI 14 · {label}</p>
      <p className="chart-guide-lede">
        Reading: <strong>{fmt(rsi)}</strong> — {zoneText}
      </p>
      <p className="chart-guide-why">{guideWhy(guide, 'rsi_14') || guideBlurb(guide, 'rsi_14')}</p>
      <div className="chart-guide-block">
        <p className="chart-guide-sub">Reference lines</p>
        <p className="chart-guide-why"><strong>70</strong> — overbought zone (red dashed).</p>
        <p className="chart-guide-why"><strong>50</strong> — midpoint; above favors bulls on this oscillator.</p>
        <p className="chart-guide-why"><strong>30</strong> — oversold zone (green dashed).</p>
      </div>
    </div>
  )
}

function AtrGuideBody({ row, label, guide }) {
  const atr = row?.atr_14
  const pct = row?.atr_pct
  return (
    <div className="chart-guide-tip">
      <p className="chart-guide-kicker">ATR 14 · {label}</p>
      <p className="chart-guide-lede">
        Reading: <strong>{fmt(atr)}</strong>
        {pct != null ? ` · ${fmt(pct)}% of price` : ''}
      </p>
      <p className="chart-guide-why">{guideWhy(guide, 'atr_14') || guideBlurb(guide, 'atr_14')}</p>
      {row?.atr_upper != null && row?.atr_lower != null && (
        <div className="chart-guide-block">
          <p className="chart-guide-sub">Bands on candle chart</p>
          <p className="chart-guide-why"><strong>ATR +1</strong> — {fmt(row.atr_upper)} (close + ATR).</p>
          <p className="chart-guide-why"><strong>ATR −1</strong> — {fmt(row.atr_lower)} (close − ATR).</p>
        </div>
      )}
    </div>
  )
}

function MacdGuideBody({ row, label, guide }) {
  const hist = Number(row?.macd_hist)
  const histTone = hist > 0 ? 'bullish momentum' : hist < 0 ? 'bearish momentum' : 'flat'
  return (
    <div className="chart-guide-tip">
      <p className="chart-guide-kicker">MACD · {label}</p>
      <p className="chart-guide-lede">
        Histogram {hist >= 0 ? 'green' : 'red'} — {histTone}.
      </p>
      <dl className="chart-guide-dl">
        <div>
          <dt>MACD line</dt>
          <dd>{fmt(row.macd)} — {guideBlurb(guide, 'macd')}</dd>
        </div>
        <div>
          <dt>Signal</dt>
          <dd>{fmt(row.macd_signal)} — {guideBlurb(guide, 'macd_signal')}</dd>
        </div>
        <div>
          <dt>Histogram</dt>
          <dd>{fmt(row.macd_hist)} — {guideWhy(guide, 'macd_hist')}</dd>
        </div>
      </dl>
    </div>
  )
}

function AreaGuideBody({ row, label, guide }) {
  return (
    <div className="chart-guide-tip">
      <p className="chart-guide-kicker">Price history · {label}</p>
      <p className="chart-guide-lede">
        Adjusted close <strong>{fmt(row.close)}</strong>
      </p>
      <p className="chart-guide-why">
        {guideBlurb(guide, 'adjusted_close')
          || 'Adjusted close splits dividends and corporate actions so long-term trends are comparable.'}
      </p>
      <p className="chart-guide-why">
        The shaded area shows the path of price over time — steep rises = strong trends; flat stretches = consolidation.
      </p>
    </div>
  )
}

export function ChartGuideToggle({ active, onToggle, label = 'Chart guide' }) {
  return (
    <button
      type="button"
      className={`ghost chart-guide-btn${active ? ' is-active' : ''}`}
      onClick={() => onToggle(v => !v)}
      aria-pressed={active}
      title={active ? 'Chart guide on — hover bars to learn' : 'Turn on chart guide — hover to explain'}
    >
      <span className="chart-guide-icon" aria-hidden="true">?</span>
      {active ? 'Guide on' : 'Guide'}
    </button>
  )
}

export function ChartGuideBanner({ active }) {
  if (!active) return null
  return (
    <p className="chart-guide-banner" role="status">
      Chart guide is on — move your cursor over any bar or point to see what it means.
    </p>
  )
}

export function ChartGuideTooltip({
  chartKind,
  guideMode,
  guide,
  active,
  payload,
  label,
  candleOpts = {},
}) {
  if (!active || !payload?.length) return null
  const row = payload[0]?.payload || {}

  if (!guideMode) {
    return <DefaultChartTooltip active={active} payload={payload} label={label} />
  }

  switch (chartKind) {
    case 'candle':
      return (
        <CandleGuideBody row={row} label={label} guide={guide} {...candleOpts} />
      )
    case 'rsi':
      return <RsiGuideBody row={row} label={label} guide={guide} />
    case 'atr':
      return <AtrGuideBody row={row} label={label} guide={guide} />
    case 'macd':
      return <MacdGuideBody row={row} label={label} guide={guide} />
    case 'area':
      return <AreaGuideBody row={row} label={label} guide={guide} />
    default:
      return <DefaultChartTooltip active={active} payload={payload} label={label} />
  }
}

export function useChartGuide(initial = false) {
  const [active, setActive] = useState(initial)
  return { chartGuide: active, setChartGuide: setActive, toggleChartGuide: () => setActive(v => !v) }
}

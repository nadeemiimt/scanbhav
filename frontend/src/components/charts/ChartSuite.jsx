import { useMemo, useState } from 'react'
import {
  Area, AreaChart, Bar, CartesianGrid, Cell, ComposedChart, Legend,
  Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { ChartGuideBanner, ChartGuideToggle, ChartGuideTooltip, useChartGuide } from '../../ChartGuide'
import { aggregateTimeframe } from '../../deskFeatures'
import { number } from '../../utils/analysisFormatters'

export function ChartSuite({ candleData, chartData, levels, session, priceLevels = [], guide = {}, extended = null }) {
  const [tf, setTf] = useState('1D')
  const [showVwap, setShowVwap] = useState(true)
  const [showLevels, setShowLevels] = useState(false)
  const [showPrior, setShowPrior] = useState(true)
  const [showDraw, setShowDraw] = useState(true)
  const [showIchimoku, setShowIchimoku] = useState(false)
  const [showFib, setShowFib] = useState(false)
  const [showKeltner, setShowKeltner] = useState(false)
  const [showAtrBands, setShowAtrBands] = useState(true)
  const ich = extended?.indicators?.ichimoku || {}
  const fib = extended?.indicators?.fibonacci || {}
  const kelt = extended?.indicators?.keltner || {}
  const fibLevels = fib.levels || {}
  const { chartGuide, setChartGuide } = useChartGuide(false)
  const candleGuideOpts = useMemo(() => ({
    showVwap,
    showLevels,
    showPrior,
    session,
    levels,
  }), [showVwap, showLevels, showPrior, session, levels])
  const baseCandles = candleData?.length
    ? candleData
    : chartData.map(d => ({ date: d.date, close: d.close, open: d.close, high: d.close, low: d.close }))
  const candles = useMemo(() => aggregateTimeframe(baseCandles, tf), [baseCandles, tf])
  const rsiSeries = useMemo(() => (
    (candles || []).map(d => ({
      ...d,
      rsi_14: d.rsi_14 == null || Number.isNaN(Number(d.rsi_14)) ? null : Number(d.rsi_14),
    }))
  ), [candles])
  const lastRsi = [...rsiSeries].reverse().find(d => d.rsi_14 != null)?.rsi_14
  const rsiZone = lastRsi == null ? '—' : lastRsi >= 70 ? 'overbought' : lastRsi <= 30 ? 'oversold' : 'neutral zone'
  const atrSeries = useMemo(() => (
    (candles || []).map(d => ({
      ...d,
      atr_14: d.atr_14 == null || Number.isNaN(Number(d.atr_14)) ? null : Number(d.atr_14),
      atr_pct: d.atr_pct == null || Number.isNaN(Number(d.atr_pct)) ? null : Number(d.atr_pct),
    }))
  ), [candles])
  const lastAtr = [...atrSeries].reverse().find(d => d.atr_14 != null)
  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <div><p className="eyebrow">CANDLE CHART</p><h3>OHLC · SMA · levels</h3></div>
          <div className="chart-toolbar">
            <ChartGuideToggle active={chartGuide} onToggle={setChartGuide} />
            {['1D', '1W', '1M'].map(t => (
              <button key={t} type="button" className={`ghost chart-tf ${tf === t ? 'active' : ''}`} onClick={() => setTf(t)}>{t}</button>
            ))}
            <label className="refresh-toggle">
              <input type="checkbox" checked={showVwap} onChange={e => setShowVwap(e.target.checked)} />
              VWAP
            </label>
            <label className="refresh-toggle">
              <input type="checkbox" checked={showLevels} onChange={e => setShowLevels(e.target.checked)} />
              Pivot
            </label>
            <label className="refresh-toggle">
              <input type="checkbox" checked={showPrior} onChange={e => setShowPrior(e.target.checked)} />
              Prior day
            </label>
            <label className="refresh-toggle">
              <input type="checkbox" checked={showDraw} onChange={e => setShowDraw(e.target.checked)} />
              Draw levels
            </label>
            <label className="refresh-toggle">
              <input type="checkbox" checked={showAtrBands} onChange={e => setShowAtrBands(e.target.checked)} />
              ATR bands
            </label>
            {extended && (
              <>
                <label className="refresh-toggle">
                  <input type="checkbox" checked={showIchimoku} onChange={e => setShowIchimoku(e.target.checked)} />
                  Ichimoku
                </label>
                <label className="refresh-toggle">
                  <input type="checkbox" checked={showFib} onChange={e => setShowFib(e.target.checked)} />
                  Fib
                </label>
                <label className="refresh-toggle">
                  <input type="checkbox" checked={showKeltner} onChange={e => setShowKeltner(e.target.checked)} />
                  Keltner
                </label>
              </>
            )}
            <span className="subtle">{candles.length} bars</span>
          </div>
        </div>
        <ChartGuideBanner active={chartGuide} />
        <div className={`chart chart-tall${chartGuide ? ' chart-guide-active' : ''}`}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={candles}>
              <CartesianGrid stroke="#243447" vertical={false} />
              <XAxis dataKey="date" minTickGap={50} tick={{ fill: '#93a4b8', fontSize: 11 }} />
              <YAxis domain={['auto', 'auto']} tick={{ fill: '#93a4b8', fontSize: 11 }} width={64} />
              <Tooltip
                cursor={{ stroke: '#e8b84a', strokeOpacity: 0.35 }}
                content={props => (
                  <ChartGuideTooltip
                    {...props}
                    chartKind="candle"
                    guideMode={chartGuide}
                    guide={guide}
                    candleOpts={candleGuideOpts}
                  />
                )}
              />
              <Bar dataKey="high" shape={<CandleStick />} isAnimationActive={false} />
              <Line type="monotone" dataKey="sma_20" stroke="#e8b84a" dot={false} strokeWidth={1.5} name="SMA20" />
              <Line type="monotone" dataKey="sma_50" stroke="#6ea8fe" dot={false} strokeWidth={1.5} name="SMA50" />
              {showVwap && <Line type="monotone" dataKey="vwap" stroke="#c4a5f5" dot={false} strokeWidth={1.25} name="VWAP" connectNulls />}
              {showLevels && levels?.pivot != null && (
                <ReferenceLine y={levels.pivot} stroke="#93a4b8" strokeDasharray="4 4" label={{ value: 'P', fill: '#93a4b8', fontSize: 10 }} />
              )}
              {showLevels && levels?.r1 != null && (
                <ReferenceLine y={levels.r1} stroke="#f07178" strokeDasharray="3 3" strokeOpacity={0.7} />
              )}
              {showLevels && levels?.s1 != null && (
                <ReferenceLine y={levels.s1} stroke="#2ecf8a" strokeDasharray="3 3" strokeOpacity={0.7} />
              )}
              {showPrior && session?.prior_high != null && (
                <ReferenceLine y={session.prior_high} stroke="#f0d48a" strokeDasharray="2 4" strokeOpacity={0.65} />
              )}
              {showPrior && session?.prior_low != null && (
                <ReferenceLine y={session.prior_low} stroke="#9ec3e8" strokeDasharray="2 4" strokeOpacity={0.65} />
              )}
              {showPrior && session?.poc != null && (
                <ReferenceLine y={session.poc} stroke="#c4a5f5" strokeDasharray="4 2" strokeOpacity={0.8} label={{ value: 'POC', fill: '#c4a5f5', fontSize: 10 }} />
              )}
              {showDraw && (priceLevels || []).map(l => (
                <ReferenceLine
                  key={l.id}
                  y={l.price}
                  stroke="#e8b84a"
                  strokeDasharray="6 3"
                  strokeOpacity={0.85}
                  label={{ value: number.format(l.price), fill: '#e8b84a', fontSize: 10 }}
                />
              ))}
              {showIchimoku && ich.cloud_top != null && (
                <ReferenceLine y={ich.cloud_top} stroke="#2ecf8a" strokeDasharray="2 6" strokeOpacity={0.55} label={{ value: 'Cloud↑', fill: '#2ecf8a', fontSize: 9 }} />
              )}
              {showIchimoku && ich.cloud_bottom != null && (
                <ReferenceLine y={ich.cloud_bottom} stroke="#f07178" strokeDasharray="2 6" strokeOpacity={0.55} label={{ value: 'Cloud↓', fill: '#f07178', fontSize: 9 }} />
              )}
              {showIchimoku && ich.tenkan != null && (
                <ReferenceLine y={ich.tenkan} stroke="#93a4b8" strokeOpacity={0.6} />
              )}
              {showIchimoku && ich.kijun != null && (
                <ReferenceLine y={ich.kijun} stroke="#6ea8fe" strokeOpacity={0.6} />
              )}
              {showFib && Object.entries(fibLevels).map(([k, v]) => (
                <ReferenceLine key={k} y={v} stroke="#c4a5f5" strokeDasharray="3 5" strokeOpacity={0.45} label={{ value: k, fill: '#c4a5f5', fontSize: 8 }} />
              ))}
              {showKeltner && kelt.upper != null && (
                <ReferenceLine y={kelt.upper} stroke="#f0d48a" strokeDasharray="4 4" strokeOpacity={0.5} />
              )}
              {showKeltner && kelt.lower != null && (
                <ReferenceLine y={kelt.lower} stroke="#f0d48a" strokeDasharray="4 4" strokeOpacity={0.5} />
              )}
              {showAtrBands && (
                <>
                  <Line type="monotone" dataKey="atr_upper" stroke="#f0d48a" dot={false} strokeWidth={1} strokeDasharray="4 3" name="ATR +1" connectNulls />
                  <Line type="monotone" dataKey="atr_lower" stroke="#9ec3e8" dot={false} strokeWidth={1} strokeDasharray="4 3" name="ATR −1" connectNulls />
                </>
              )}
              <Legend />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <div><p className="eyebrow">OSCILLATORS</p><h3>RSI 14</h3></div>
          <div className="chart-toolbar">
            <ChartGuideToggle active={chartGuide} onToggle={setChartGuide} />
            <span className="subtle">
              {lastRsi != null ? `${number.format(lastRsi)} · ${rsiZone}` : 'No RSI series'}
            </span>
          </div>
        </div>
        <div className={`chart${chartGuide ? ' chart-guide-active' : ''}`}>
          {rsiSeries.some(d => d.rsi_14 != null) ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChartSafe data={rsiSeries} dataKey="rsi_14" stroke="#e8b84a" guideMode={chartGuide} guide={guide} />
            </ResponsiveContainer>
          ) : (
            <p className="subtle chart-empty">RSI needs at least 14 sessions of closes. Re-run Analyze after loading fuller history.</p>
          )}
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <div><p className="eyebrow">VOLATILITY</p><h3>ATR 14</h3></div>
          <div className="chart-toolbar">
            <ChartGuideToggle active={chartGuide} onToggle={setChartGuide} />
            <span className="subtle">
              {lastAtr
                ? `${number.format(lastAtr.atr_14)} · ${number.format(lastAtr.atr_pct)}% of price`
                : 'No ATR series'}
            </span>
          </div>
        </div>
        <div className={`chart${chartGuide ? ' chart-guide-active' : ''}`}>
          {atrSeries.some(d => d.atr_14 != null) ? (
            <ResponsiveContainer width="100%" height="100%">
              <AtrChart data={atrSeries} guideMode={chartGuide} guide={guide} />
            </ResponsiveContainer>
          ) : (
            <p className="subtle chart-empty">ATR needs at least 14 sessions. Re-run Analyze after loading fuller history.</p>
          )}
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <div><p className="eyebrow">MACD</p><h3>Line · Signal · Histogram</h3></div>
          <ChartGuideToggle active={chartGuide} onToggle={setChartGuide} />
        </div>
        <div className={`chart${chartGuide ? ' chart-guide-active' : ''}`}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={candles}>
              <CartesianGrid stroke="#243447" vertical={false} />
              <XAxis dataKey="date" minTickGap={50} tick={{ fill: '#93a4b8', fontSize: 11 }} />
              <YAxis tick={{ fill: '#93a4b8', fontSize: 11 }} width={64} />
              <Tooltip
                cursor={{ stroke: '#e8b84a', strokeOpacity: 0.35 }}
                content={props => (
                  <ChartGuideTooltip {...props} chartKind="macd" guideMode={chartGuide} guide={guide} />
                )}
              />
              <Bar dataKey="macd_hist" name="Hist">
                {candles.map((entry, i) => (
                  <Cell key={`m${i}`} fill={(entry.macd_hist || 0) >= 0 ? '#2ecf8a' : '#f07178'} />
                ))}
              </Bar>
              <Line type="monotone" dataKey="macd" stroke="#e8b84a" dot={false} strokeWidth={1.5} />
              <Line type="monotone" dataKey="macd_signal" stroke="#6ea8fe" dot={false} strokeWidth={1.5} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <div><p className="eyebrow">PRICE</p><h3>Adjusted close (full history)</h3></div>
          <div className="chart-toolbar">
            <ChartGuideToggle active={chartGuide} onToggle={setChartGuide} />
            <span>{chartData.length} candles</span>
          </div>
        </div>
        <div className={`chart${chartGuide ? ' chart-guide-active' : ''}`}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="price" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="5%" stopColor="#2ecf8a" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#2ecf8a" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#243447" vertical={false} />
              <XAxis dataKey="date" minTickGap={60} tick={{ fill: '#93a4b8', fontSize: 12 }} />
              <YAxis domain={['auto', 'auto']} tick={{ fill: '#93a4b8', fontSize: 12 }} width={70} />
              <Tooltip
                cursor={{ stroke: '#2ecf8a', strokeOpacity: 0.35 }}
                content={props => (
                  <ChartGuideTooltip {...props} chartKind="area" guideMode={chartGuide} guide={guide} />
                )}
              />
              <Area type="monotone" dataKey="close" stroke="#2ecf8a" fill="url(#price)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </section>
    </>
  )
}

function AtrChart({ data, width, height, guideMode = false, guide = {} }) {
  const w = width || '100%'
  const h = height || '100%'
  return (
    <ComposedChart data={data} width={w} height={h} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
      <CartesianGrid stroke="#243447" vertical={false} />
      <XAxis dataKey="date" minTickGap={50} tick={{ fill: '#93a4b8', fontSize: 11 }} />
      <YAxis yAxisId="atr" tick={{ fill: '#93a4b8', fontSize: 11 }} width={48} />
      <YAxis yAxisId="pct" orientation="right" tick={{ fill: '#93a4b8', fontSize: 11 }} width={40} />
      <Tooltip
        cursor={{ stroke: '#e8b84a', strokeOpacity: 0.35 }}
        content={props => (
          <ChartGuideTooltip {...props} chartKind="atr" guideMode={guideMode} guide={guide} />
        )}
      />
      <Area yAxisId="atr" type="monotone" dataKey="atr_14" stroke="#f0d48a" fill="#f0d48a" fillOpacity={0.15} strokeWidth={2} connectNulls name="ATR 14" />
      <Line yAxisId="pct" type="monotone" dataKey="atr_pct" stroke="#6ea8fe" dot={false} strokeWidth={1.5} connectNulls name="ATR %" />
    </ComposedChart>
  )
}

function LineChartSafe({ data, dataKey, stroke, width, height, guideMode = false, guide = {} }) {
  // ResponsiveContainer injects width/height — must forward them or the plot stays blank.
  const w = width || '100%'
  const h = height || '100%'
  return (
    <ComposedChart data={data} width={w} height={h} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
      <CartesianGrid stroke="#243447" vertical={false} />
      <XAxis dataKey="date" minTickGap={50} tick={{ fill: '#93a4b8', fontSize: 11 }} />
      <YAxis domain={[0, 100]} ticks={[0, 30, 50, 70, 100]} tick={{ fill: '#93a4b8', fontSize: 11 }} width={40} />
      <Tooltip
        cursor={{ stroke: '#e8b84a', strokeOpacity: 0.35 }}
        content={props => (
          <ChartGuideTooltip {...props} chartKind="rsi" guideMode={guideMode} guide={guide} />
        )}
      />
      <ReferenceLine y={70} stroke="#f07178" strokeDasharray="4 4" strokeOpacity={0.7} />
      <ReferenceLine y={30} stroke="#2ecf8a" strokeDasharray="4 4" strokeOpacity={0.7} />
      <ReferenceLine y={50} stroke="#93a4b8" strokeDasharray="2 6" strokeOpacity={0.45} />
      <Line
        type="monotone"
        dataKey={dataKey}
        stroke={stroke}
        dot={false}
        strokeWidth={2}
        connectNulls
        isAnimationActive={false}
        name="RSI 14"
      />
    </ComposedChart>
  )
}

function CandleStick(props) {
  const { x, width, payload } = props
  if (!payload || payload.open == null) return null
  const { open, close, high, low } = payload
  const isUp = close >= open
  const color = isUp ? '#2ecf8a' : '#f07178'
  const scale = props.yAxis?.scale
  if (typeof scale !== 'function') {
    // Fallback: approximate using bar geometry for close value
    const { y, height } = props
    if (y == null || !height) return null
    const cx = x + width / 2
    return (
      <g>
        <line x1={cx} x2={cx} y1={y} y2={y + Math.max(height * 0.15, 4)} stroke={color} strokeWidth={1} />
        <rect x={x + width * 0.2} y={y} width={Math.max(width * 0.6, 2)} height={Math.max(height * 0.12, 2)} fill={color} />
      </g>
    )
  }
  const yOpen = scale(open)
  const yClose = scale(close)
  const yHigh = scale(high)
  const yLow = scale(low)
  const bodyTop = Math.min(yOpen, yClose)
  const bodyH = Math.max(Math.abs(yClose - yOpen), 1.5)
  const cx = x + width / 2
  return (
    <g>
      <line x1={cx} x2={cx} y1={yHigh} y2={yLow} stroke={color} strokeWidth={1} />
      <rect x={x + width * 0.22} y={bodyTop} width={Math.max(width * 0.56, 2)} height={bodyH} fill={isUp ? color : '#0b1520'} stroke={color} strokeWidth={1} />
    </g>
  )
}


import { ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

const money = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 })

export function SwingMiniChart({ candles, entry, stop, targets = [] }) {
  if (!candles?.length) {
    return <p className="subtle swing-chart-empty">Run scan for price history chart.</p>
  }
  const data = candles.map(c => ({
    date: c.date,
    close: Number(c.close),
  })).filter(d => d.close > 0)

  const lines = [
    entry != null && entry > 0 ? { y: Number(entry), stroke: '#e8b84a', label: 'Entry' } : null,
    stop != null && stop > 0 ? { y: Number(stop), stroke: '#f87171', label: 'Stop' } : null,
    ...targets.filter(t => t > 0).map((t, i) => ({
      y: Number(t),
      stroke: '#34d399',
      label: `T${i + 1}`,
    })),
  ].filter(Boolean)

  return (
    <div className="swing-mini-chart">
      <ResponsiveContainer width="100%" height={180}>
        <ComposedChart data={data}>
          <XAxis dataKey="date" tick={{ fill: '#93a4b8', fontSize: 10 }} minTickGap={40} />
          <YAxis domain={['auto', 'auto']} tick={{ fill: '#93a4b8', fontSize: 10 }} width={52} />
          <Tooltip
            formatter={v => money.format(v)}
            labelStyle={{ color: '#93a4b8' }}
            contentStyle={{ background: '#0f1724', border: '1px solid #243447' }}
          />
          <Line type="monotone" dataKey="close" stroke="#60a5fa" dot={false} strokeWidth={1.5} />
          {lines.map(l => (
            <ReferenceLine
              key={`${l.label}-${l.y}`}
              y={l.y}
              stroke={l.stroke}
              strokeDasharray="4 4"
              label={{ value: l.label, fill: l.stroke, fontSize: 10 }}
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

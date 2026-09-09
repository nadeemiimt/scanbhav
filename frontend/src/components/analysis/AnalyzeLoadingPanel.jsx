import { useEffect, useState } from 'react'

const STEPS = [
  'Fetching OHLCV history',
  'Computing moving averages & momentum',
  'Scoring 1D → 5Y horizons',
  'Running extended factors',
  'Assembling research dossier',
]

export function AnalyzeLoadingPanel({ symbol }) {
  const [step, setStep] = useState(0)

  useEffect(() => {
    setStep(0)
    const timer = setInterval(() => {
      setStep(prev => (prev + 1) % STEPS.length)
    }, 1100)
    return () => clearInterval(timer)
  }, [symbol])

  return (
    <section className="panel analyze-loading" aria-live="polite" aria-busy="true">
      <div className="analyze-loading-head">
        <div className="analyze-scan-radar" aria-hidden="true">
          <span className="analyze-scan-arc" />
          <span className="analyze-scan-sweep" />
          <span className="analyze-scan-dot" />
        </div>
        <div>
          <p className="eyebrow">SCANNING</p>
          <h3>{symbol || 'Stock'}</h3>
          <p className="subtle analyze-loading-step">{STEPS[step]}…</p>
        </div>
      </div>
      <ul className="analyze-loading-steps">
        {STEPS.map((label, i) => (
          <li
            key={label}
            className={[i < step && 'done', i === step && 'active'].filter(Boolean).join(' ') || undefined}
          >
            <span className="analyze-step-dot" aria-hidden="true" />
            {label}
          </li>
        ))}
      </ul>
      <div className="analyze-skeleton-grid" aria-hidden="true">
        <div className="analyze-skeleton-block wide" />
        <div className="analyze-skeleton-block" />
        <div className="analyze-skeleton-block" />
        <div className="analyze-skeleton-block tall" />
      </div>
    </section>
  )
}

export default AnalyzeLoadingPanel

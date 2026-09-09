import { PlatformLimitationsPanel } from '../components/analysis/PlatformLimitations'
import { APP_NAME } from '../brand'

export function AboutPage({ go, onGuide }) {
  return (
    <section className="content-page">
      <p className="eyebrow">About</p>
      <h2>{APP_NAME}</h2>
      <p>
        {APP_NAME} is your local neural research desk — scan the bhav, score horizons, and run
        a full Indian equity workspace with screener, swing, autopilot, and GenAI agents.
      </p>
      <div className="content-grid">
        <article className="content-card">
          <h4>Analyze</h4>
          <p>Full indicator readout, charts, and horizon ratings.</p>
          <button className="primary" style={{ marginTop: 12 }} onClick={() => go('single')}>Open Analyze</button>
        </article>
        <article className="content-card">
          <h4>Coach</h4>
          <p>Advisor, Ask books, practice trades, SIP math, and glossary.</p>
          <button className="primary" style={{ marginTop: 12 }} onClick={() => go('coach')}>Open Coach</button>
        </article>
        <article className="content-card">
          <h4>First visit?</h4>
          <p>Run the guided path — goal, risk, starter name, then Analyze.</p>
          <button className="primary" style={{ marginTop: 12 }} onClick={() => onGuide?.()}>Guide me</button>
        </article>
      </div>
      <PlatformLimitationsPanel defaultOpen className="about-limits" />
      <p className="subtle" style={{ marginTop: 18 }}>Educational use only — not investment advice.</p>
    </section>
  )
}

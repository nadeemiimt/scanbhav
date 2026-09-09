import { useEffect, useState } from 'react'
import { apiGet, apiGetOptional, apiPost, apiPostForm } from './lib/apiClient'
import { money, number } from './utils/analysisFormatters'
import { useAuth } from './context/AuthContext'

const SAMPLE_JSON = `{
  "holdings": [
    {
      "asset_type": "stock",
      "symbol": "RELIANCE.NSE",
      "name": "Reliance Industries",
      "quantity": 10,
      "avg_cost": 1200,
      "current_price": 1290
    },
    {
      "asset_type": "mutual_fund",
      "name": "Parag Parikh Flexi Cap",
      "quantity": 100,
      "avg_cost": 65,
      "current_price": 78
    }
  ]
}`

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export default function PersonalAdvisor({ provider, onError }) {
  const { user, authenticated } = useAuth()
  const [email, setEmail] = useState(() => localStorage.getItem('advisorEmail') || '')
  const [emailError, setEmailError] = useState('')
  const [profiles, setProfiles] = useState([])
  const [profileId, setProfileId] = useState(() => localStorage.getItem('advisorProfileId') || '')
  const [profileName, setProfileName] = useState('My portfolio')
  const [risk, setRisk] = useState('moderate')
  const [profile, setProfile] = useState(null)
  const [jsonText, setJsonText] = useState(SAMPLE_JSON)
  const [file, setFile] = useState(null)
  const [visionProvider, setVisionProvider] = useState('openai')
  const [visionModel, setVisionModel] = useState('')
  const [visionInfo, setVisionInfo] = useState(null)
  const [advice, setAdvice] = useState(null)
  const [busy, setBusy] = useState('')

  useEffect(() => {
    apiGetOptional('/api/advisor/vision-config')
      .then(data => {
        if (!data) return
        setVisionInfo(data)
        setVisionProvider(data.provider || 'openai')
        setVisionModel(data.model || '')
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (authenticated && user?.email) {
      setEmail(user.email)
      localStorage.setItem('advisorEmail', user.email)
    }
  }, [authenticated, user?.email])

  function validateEmail(value) {
    const trimmed = value.trim()
    if (!EMAIL_RE.test(trimmed)) {
      setEmailError('Enter a valid email (e.g. you@example.com)')
      return null
    }
    setEmailError('')
    return trimmed.toLowerCase()
  }

  async function loadProfiles(nextEmail = email) {
    const valid = validateEmail(nextEmail)
    if (!valid) return
    onError('')
    setBusy('profiles')
    try {
      localStorage.setItem('advisorEmail', valid)
      const result = await apiGet(`/api/advisor/profiles?email=${encodeURIComponent(valid)}`)
      setProfiles(result.profiles || [])
      if (result.profiles?.length) {
        const preferred = result.profiles.find(p => p.id === profileId) || result.profiles[0]
        setProfileId(preferred.id)
        await loadProfile(valid, preferred.id)
      } else {
        setProfile(null)
        setAdvice(null)
      }
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy('')
    }
  }

  async function loadProfile(nextEmail, id) {
    const result = await apiGet(`/api/advisor/profiles/${id}?email=${encodeURIComponent(nextEmail)}`)
    setProfile(result)
    localStorage.setItem('advisorProfileId', id)
  }

  async function createProfile() {
    const valid = validateEmail(email)
    if (!valid) return
    onError('')
    setBusy('create')
    try {
      const result = await apiPost('/api/advisor/profiles', { email: valid, name: profileName, risk_tolerance: risk })
      setProfileId(result.id)
      setProfile(result)
      await loadProfiles(valid)
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy('')
    }
  }

  async function ingestJson() {
    const valid = validateEmail(email)
    if (!valid || !profileId) return onError('Select a valid email profile first.')
    onError('')
    setBusy('json')
    try {
      const portfolio = JSON.parse(jsonText)
      const result = await apiPost('/api/advisor/ingest/json', { email: valid, profile_id: profileId, portfolio })
      setProfile(result.profile)
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy('')
    }
  }

  async function ingestScreenshot() {
    const valid = validateEmail(email)
    if (!valid || !profileId) return onError('Select a valid email profile first.')
    if (!file) return onError('Choose a portfolio screenshot first.')
    onError('')
    setBusy('shot')
    try {
      const body = new FormData()
      body.append('email', valid)
      body.append('profile_id', profileId)
      body.append('provider', visionProvider)
      if (visionModel) body.append('model', visionModel)
      body.append('file', file)
      const result = await apiPostForm('/api/advisor/ingest/screenshot', body)
      setProfile(result.profile)
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy('')
    }
  }

  async function runAdvisor(withAi = true) {
    const valid = validateEmail(email)
    if (!valid || !profileId) return onError('Select a valid email profile first.')
    onError('')
    setBusy(withAi ? 'advise-ai' : 'advise')
    try {
      const result = await apiPost('/api/advisor/run', {
        email: valid, profile_id: profileId, provider, with_ai: withAi,
      })
      setAdvice(result)
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy('')
    }
  }

  return (
    <section className="panel feature-panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">PERSONAL ADVISOR</p>
          <h3>Track stocks & mutual funds · exit-review alerts</h3>
        </div>
      </div>

      <div className="advisor-grid">
        <div className="advisor-card">
          <h4>1. Email & profiles</h4>
          <label>
            Email
            <input
              value={email}
              onChange={e => { setEmail(e.target.value); setEmailError('') }}
              placeholder="you@example.com"
            />
          </label>
          {emailError && <p className="field-error">{emailError}</p>}
          {authenticated && user?.email && (
            <p className="subtle">Signed in as {user.email}</p>
          )}
          <div className="feature-controls">
            <button className="ghost" onClick={() => loadProfiles()} disabled={!!busy}>
              {busy === 'profiles' ? 'Loading…' : 'Load profiles'}
            </button>
          </div>
          <label>
            New profile name
            <input value={profileName} onChange={e => setProfileName(e.target.value)} />
          </label>
          <label>
            Risk tolerance
            <select value={risk} onChange={e => setRisk(e.target.value)}>
              <option value="conservative">Conservative</option>
              <option value="moderate">Moderate</option>
              <option value="aggressive">Aggressive</option>
            </select>
          </label>
          <button className="primary" onClick={createProfile} disabled={!!busy}>
            {busy === 'create' ? 'Creating…' : 'Create profile'}
          </button>
          {profiles.length > 0 && (
            <label>
              Active profile
              <select
                value={profileId}
                onChange={async e => {
                  const id = e.target.value
                  setProfileId(id)
                  setAdvice(null)
                  try {
                    await loadProfile(email.trim().toLowerCase(), id)
                  } catch (err) {
                    onError(err.message)
                  }
                }}
              >
                {profiles.map(p => (
                  <option key={p.id} value={p.id}>
                    {p.name} · {p.holding_count || 0} holdings
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>

        <div className="advisor-card">
          <h4>2. Ingest portfolio</h4>
          <p className="subtle">Paste JSON or upload a brokerage / MF screenshot. AI cleanses, then stores under your email profile.</p>
          <label>
            Portfolio JSON
            <textarea rows={12} value={jsonText} onChange={e => setJsonText(e.target.value)} />
          </label>
          <button className="ghost" onClick={ingestJson} disabled={!!busy || !profileId}>
            {busy === 'json' ? 'Cleansing…' : 'Ingest JSON'}
          </button>

          <hr className="soft" />

          <label>
            Screenshot
            <input type="file" accept="image/*" onChange={e => setFile(e.target.files?.[0] || null)} />
          </label>
          <label>
            Vision provider
            <select value={visionProvider} onChange={e => setVisionProvider(e.target.value)}>
              {(visionInfo?.supported_providers || ['openai', 'openai_compatible', 'cursor', 'ollama']).map(p => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </label>
          <label>
            Vision model
            <input value={visionModel} onChange={e => setVisionModel(e.target.value)} placeholder="gpt-4o-mini or llava" />
          </label>
          <button className="primary" onClick={ingestScreenshot} disabled={!!busy || !profileId}>
            {busy === 'shot' ? 'Reading screenshot…' : 'Ingest screenshot'}
          </button>
          <p className="subtle">Default from server: {visionInfo ? `${visionInfo.provider} / ${visionInfo.model}` : '…'}. Configure keys in `.env`.</p>
        </div>
      </div>

      {profile && (
        <div className="ai-card">
          <p className="eyebrow">PROFILE · {profile.email}</p>
          <h4>{profile.name} · {profile.risk_tolerance} · {(profile.holdings || []).length} holdings</h4>
          {(profile.holdings || []).length === 0 ? (
            <p className="subtle">No holdings yet — ingest JSON or a screenshot.</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Type</th><th>Symbol / name</th><th>Qty</th><th>Avg cost</th><th>Current</th><th>Invested</th>
                  </tr>
                </thead>
                <tbody>
                  {profile.holdings.map(h => (
                    <tr key={h.id}>
                      <td>{h.asset_type}</td>
                      <td>{h.symbol || h.name}</td>
                      <td>{h.quantity != null ? number.format(h.quantity) : '—'}</td>
                      <td>{h.avg_cost != null ? number.format(h.avg_cost) : '—'}</td>
                      <td>{h.current_price != null ? number.format(h.current_price) : '—'}</td>
                      <td>{h.invested_value != null ? money.format(h.invested_value) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="feature-controls">
            <button className="ghost" onClick={() => runAdvisor(false)} disabled={!!busy || !(profile.holdings || []).length}>
              {busy === 'advise' ? 'Scoring…' : 'Rule-based check'}
            </button>
            <button className="primary" onClick={() => runAdvisor(true)} disabled={!!busy || !(profile.holdings || []).length}>
              {busy === 'advise-ai' ? 'Advising…' : 'Run personal advisor'}
            </button>
          </div>
        </div>
      )}

      {advice && (
        <>
          <div className="paper-rank">
            <article className={(advice.totals?.pnl || 0) >= 0 ? 'gain' : 'loss'}>
              <p className="eyebrow">PORTFOLIO P&L</p>
              <h3 className={(advice.totals?.pnl || 0) >= 0 ? 'up' : 'down'}>
                {advice.totals?.pnl_pct != null ? `${advice.totals.pnl_pct >= 0 ? '+' : ''}${number.format(advice.totals.pnl_pct)}%` : '—'}
              </h3>
              <p>{money.format(advice.totals?.pnl || 0)} on {money.format(advice.totals?.invested_value || 0)}</p>
            </article>
            <article className={advice.exit_candidates?.length ? 'loss' : 'gain'}>
              <p className="eyebrow">EXIT REVIEWS</p>
              <h3>{advice.exit_candidates?.length || 0}</h3>
              <p>names flagged for attention / exit review</p>
            </article>
          </div>

          {advice.ai && (
            <div className="ai-card">
              <p className="eyebrow">AI COACH</p>
              <h4>{advice.ai.headline}</h4>
              <p>{advice.ai.summary}</p>
              <div className="insight-columns">
                <div>
                  <h4>Priority exits</h4>
                  <ul>
                    {(advice.ai.priority_exits || []).map((item, i) => (
                      <li key={i}><b>{item.symbol_or_name}</b> — {item.why} ({item.suggested_stance})</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h4>Keep watching</h4>
                  <ul>{(advice.ai.keep_watching || []).map((item, i) => <li key={i}>{item}</li>)}</ul>
                </div>
                <div>
                  <h4>Process tips</h4>
                  <ul>{(advice.ai.process_tips || []).map((item, i) => <li key={i}>{item}</li>)}</ul>
                </div>
              </div>
            </div>
          )}

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Holding</th><th>P&L %</th><th>Urgency</th><th>Action</th><th>Why</th>
                </tr>
              </thead>
              <tbody>
                {(advice.holdings || []).map(h => (
                  <tr key={h.id}>
                    <td>{h.symbol || h.name}</td>
                    <td className={(h.pnl_pct ?? 0) >= 0 ? 'up' : 'down'}>
                      {h.pnl_pct != null ? `${number.format(h.pnl_pct)}%` : '—'}
                    </td>
                    <td><span className={`urgency ${h.signal?.urgency}`}>{h.signal?.urgency}</span></td>
                    <td>{(h.signal?.action || '').replaceAll('_', ' ')}</td>
                    <td className="leftish">{(h.signal?.reasons || []).join(' ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="subtle">{advice.disclaimer}</p>
        </>
      )}
    </section>
  )
}

import { useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import { APP_NAME } from '../../brand'

const ICONS = {
  google: (
    <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M21.35 11.1h-9.2v2.9h5.3c-.23 1.4-1.6 4.1-5.3 4.1-3.2 0-5.8-2.6-5.8-5.8s2.6-5.8 5.8-5.8c1.8 0 3 .8 3.7 1.5l2.5-2.4C16.9 3.6 14.8 2.5 12.45 2.5 7.55 2.5 3.5 6.55 3.5 11.45S7.55 20.4 12.45 20.4c7.2 0 8.95-5.03 8.95-7.65 0-.52-.05-.9-.15-1.15z"/></svg>
  ),
  yahoo: (
    <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M4.5 19.5 10 12 4.5 4.5h3.2L12.8 10l5.1-5.5h3.2L15.1 12l5.6 7.5h-3.2L12.8 14l-5.1 5.5H4.5z"/></svg>
  ),
  github: (
    <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.11.79-.25.79-.56 0-.28-.01-1.02-.02-2-3.2.7-3.88-1.54-3.88-1.54-.53-1.35-1.29-1.71-1.29-1.71-1.06-.72.08-.71.08-.71 1.17.08 1.79 1.2 1.79 1.2 1.04 1.78 2.73 1.27 3.4.97.11-.76.41-1.27.74-1.56-2.55-.29-5.24-1.28-5.24-5.7 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.46.11-3.04 0 0 .97-.31 3.18 1.18a11.1 11.1 0 0 1 2.9-.39c.98 0 1.97.13 2.9.39 2.2-1.49 3.17-1.18 3.17-1.18.63 1.58.23 2.75.11 3.04.74.81 1.19 1.84 1.19 3.1 0 4.43-2.7 5.4-5.28 5.68.42.36.8 1.08.8 2.18 0 1.57-.01 2.84-.01 3.22 0 .31.21.68.8.56A10.52 10.52 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5z"/></svg>
  ),
  microsoft: (
    <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#f25022" d="M3 3h9v9H3z"/><path fill="#7fba00" d="M12 3h9v9h-9z"/><path fill="#00a4ef" d="M3 12h9v9H3z"/><path fill="#ffb900" d="M12 12h9v9h-9z"/></svg>
  ),
}

export default function LoginModal() {
  const {
    loginOpen, setLoginOpen, providers, devLoginEnabled,
    loginWithProvider, devLogin, authError, setAuthError,
  } = useAuth()
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [localError, setLocalError] = useState('')

  if (!loginOpen) return null

  const configured = (providers || []).filter(p => p.configured)
  const showDev = devLoginEnabled && configured.length === 0

  async function submitDev(e) {
    e.preventDefault()
    setLocalError('')
    setAuthError('')
    setBusy(true)
    try {
      await devLogin(email, name)
    } catch (err) {
      setLocalError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-modal-backdrop" role="presentation" onClick={() => setLoginOpen(false)}>
      <div
        className="auth-modal panel"
        role="dialog"
        aria-labelledby="auth-modal-title"
        onClick={e => e.stopPropagation()}
      >
        <div className="auth-modal-glow" aria-hidden="true" />
        <div className="panel-head auth-modal-head">
          <div>
            <p className="eyebrow">SECURE ACCESS</p>
            <h3 id="auth-modal-title">Sign in to {APP_NAME}</h3>
          </div>
          <button type="button" className="ghost auth-close" onClick={() => setLoginOpen(false)} aria-label="Close">×</button>
        </div>

        <p className="subtle auth-modal-lead">
          Sync your advisor profiles, bookmarks, and desk preferences across devices.
        </p>

        {(authError || localError) && (
          <p className="auth-error">{localError || authError}</p>
        )}

        <div className="auth-provider-grid">
          {configured.map(p => (
            <button
              key={p.id}
              type="button"
              className={`auth-provider-btn auth-provider-${p.id}`}
              onClick={() => loginWithProvider(p.id)}
            >
              <span className="auth-provider-icon">{ICONS[p.icon] || ICONS.google}</span>
              <span>Continue with {p.label}</span>
            </button>
          ))}
        </div>

        {configured.length === 0 && !showDev && (
          <p className="subtle">
            Add OAuth client credentials to <code>.env</code> (see <code>.env.example</code>) to enable Google, Yahoo, GitHub, or Microsoft login.
          </p>
        )}

        {showDev && (
          <form className="auth-dev-form" onSubmit={submitDev}>
            <p className="eyebrow">LOCAL DESK MODE</p>
            <label>
              Email
              <input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" required />
            </label>
            <label>
              Display name <span className="subtle">(optional)</span>
              <input type="text" value={name} onChange={e => setName(e.target.value)} placeholder="Your name" />
            </label>
            <button type="submit" className="primary auth-dev-submit" disabled={busy}>
              {busy ? 'Signing in…' : 'Continue with email'}
            </button>
          </form>
        )}

        <p className="subtle auth-modal-foot">
          OAuth only — we never store your provider password. Research data stays on your machine.
        </p>
      </div>
    </div>
  )
}

export function AuthHeaderButton() {
  const { user, loading, setLoginOpen, logout } = useAuth()

  if (loading) {
    return <span className="auth-chip auth-chip-loading subtle">…</span>
  }

  if (user) {
    return (
      <div className="auth-user-menu">
        <button type="button" className="auth-chip auth-chip-user" onClick={() => setLoginOpen(true)} title={user.email}>
          {user.picture
            ? <img src={user.picture} alt="" className="auth-avatar" />
            : <span className="auth-avatar auth-avatar-fallback">{(user.name || user.email || '?')[0].toUpperCase()}</span>}
          <span className="auth-chip-label">{user.name?.split(' ')[0] || user.email?.split('@')[0]}</span>
        </button>
        <button type="button" className="ghost auth-signout" onClick={logout}>Sign out</button>
      </div>
    )
  }

  return (
    <button type="button" className="primary auth-signin-btn" onClick={() => setLoginOpen(true)}>
      Sign in
    </button>
  )
}

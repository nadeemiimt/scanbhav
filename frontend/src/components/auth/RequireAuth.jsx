import { useCallback } from 'react'
import { useAuth } from '../../context/AuthContext'

export function useAuthGate() {
  const { authenticated, setLoginOpen } = useAuth()

  const gate = useCallback((action) => {
    if (authenticated) {
      action?.()
      return true
    }
    setLoginOpen(true)
    return false
  }, [authenticated, setLoginOpen])

  return { authenticated, gate, promptLogin: () => setLoginOpen(true) }
}

export default function RequireAuth({
  children,
  title = 'Sign in required',
  description = 'Sign in with Google, Yahoo, or another provider to use this feature.',
}) {
  const { authenticated, loading, setLoginOpen } = useAuth()

  if (loading) {
    return (
      <section className="panel auth-gate">
        <p className="subtle">Checking session…</p>
      </section>
    )
  }

  if (!authenticated) {
    return (
      <section className="panel auth-gate">
        <p className="eyebrow">SECURE ACCESS</p>
        <h3>{title}</h3>
        <p className="subtle auth-gate-lead">{description}</p>
        <button type="button" className="primary" onClick={() => setLoginOpen(true)}>
          Sign in
        </button>
      </section>
    )
  }

  return children
}

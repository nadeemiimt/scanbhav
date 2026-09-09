import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { apiGet, apiPost } from '../lib/apiClient'
import {
  clearAuthToken,
  consumeAuthTokenFromHash,
  getAuthToken,
  readAuthErrorFromQuery,
  setAuthToken,
} from '../lib/authToken'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [providers, setProviders] = useState([])
  const [devLoginEnabled, setDevLoginEnabled] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loginOpen, setLoginOpen] = useState(false)
  const [authError, setAuthError] = useState('')

  const refreshUser = useCallback(async () => {
    const token = getAuthToken()
    if (!token) {
      setUser(null)
      return null
    }
    const data = await apiGet('/api/auth/me')
    if (data?.authenticated && data.user) {
      setUser(data.user)
      return data.user
    }
    clearAuthToken()
    setUser(null)
    return null
  }, [])

  useEffect(() => {
    let cancelled = false
    async function boot() {
      const hashToken = consumeAuthTokenFromHash()
      const queryErr = readAuthErrorFromQuery()
      if (queryErr) setAuthError(queryErr)
      if (hashToken) setAuthToken(hashToken)

      try {
        const meta = await apiGet('/api/auth/providers')
        if (!cancelled) {
          setProviders(meta?.providers || [])
          setDevLoginEnabled(!!meta?.dev_login_enabled)
        }
      } catch {
        if (!cancelled) setProviders([])
      }

      if (!cancelled) {
        await refreshUser()
        setLoading(false)
      }
    }
    boot()
    return () => { cancelled = true }
  }, [refreshUser])

  const loginWithProvider = useCallback((providerId) => {
    window.location.href = `/api/auth/login/${providerId}`
  }, [])

  const devLogin = useCallback(async (email, name = '') => {
    setAuthError('')
    const data = await apiPost('/api/auth/dev-login', { email, name })
    setAuthToken(data.token)
    setUser(data.user)
    setLoginOpen(false)
    return data.user
  }, [])

  const logout = useCallback(() => {
    clearAuthToken()
    setUser(null)
    setLoginOpen(false)
  }, [])

  const value = useMemo(() => ({
    user,
    authenticated: !!user,
    providers,
    devLoginEnabled,
    loading,
    loginOpen,
    setLoginOpen,
    authError,
    setAuthError,
    loginWithProvider,
    devLogin,
    logout,
    refreshUser,
  }), [
    user, providers, devLoginEnabled, loading, loginOpen, authError,
    loginWithProvider, devLogin, logout, refreshUser,
  ])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

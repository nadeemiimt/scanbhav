/** JWT storage for authenticated API calls. */

const TOKEN_KEY = 'scanBhavAuthToken'

export function getAuthToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || ''
  } catch {
    return ''
  }
}

export function setAuthToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* ignore quota */
  }
}

export function clearAuthToken() {
  setAuthToken('')
}

/** Read #auth_token= from OAuth redirect and strip hash. */
export function consumeAuthTokenFromHash() {
  const hash = window.location.hash || ''
  const match = hash.match(/auth_token=([^&]+)/)
  if (!match) return null
  const token = decodeURIComponent(match[1])
  setAuthToken(token)
  const cleaned = hash.replace(/[#&]?auth_token=[^&]*/, '').replace(/^#&/, '#').replace(/^#$/, '')
  const url = `${window.location.pathname}${window.location.search}${cleaned}`
  window.history.replaceState(null, '', url || window.location.pathname)
  return token
}

export function readAuthErrorFromQuery() {
  const params = new URLSearchParams(window.location.search)
  const err = params.get('auth_error')
  if (!err) return null
  params.delete('auth_error')
  const q = params.toString()
  window.history.replaceState(null, '', `${window.location.pathname}${q ? `?${q}` : ''}${window.location.hash}`)
  return err
}

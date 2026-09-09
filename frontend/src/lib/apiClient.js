/** Shared fetch wrapper for FastAPI responses. */

import { getAuthToken } from './authToken'
import { logDebug, logError } from './logger'

export function apiDetail(result) {
  if (typeof result?.detail === 'string') return result.detail
  if (Array.isArray(result?.detail)) {
    return result.detail.map(d => d.msg || JSON.stringify(d)).join('; ')
  }
  if (result?.message) return String(result.message)
  return 'Request failed'
}

export class ApiError extends Error {
  constructor(message, { status, path, body } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.path = path
    this.body = body
  }
}

/**
 * JSON API fetch with consistent error parsing.
 * @param {string} path
 * @param {RequestInit} [options]
 * @param {{ allowEmpty?: boolean }} [config]
 */
export async function apiFetch(path, options = {}, config = {}) {
  const { allowEmpty = false, timeoutMs = 25000 } = config
  logDebug('apiFetch', options.method || 'GET', path)

  const token = getAuthToken()
  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {}

  const controller = new AbortController()
  const timeout = timeoutMs > 0
    ? setTimeout(() => controller.abort(), timeoutMs)
    : null

  let response
  try {
    response = await fetch(path, {
      headers: { Accept: 'application/json', ...authHeaders, ...(options.headers || {}) },
      ...options,
      signal: controller.signal,
    })
  } catch (err) {
    if (err?.name === 'AbortError') {
      throw new ApiError(`Request timed out after ${Math.round(timeoutMs / 1000)}s — ${path}`, { path })
    }
    logError('Network error', path, err)
    throw new ApiError('Network error — is the backend running?', { path })
  } finally {
    if (timeout) clearTimeout(timeout)
  }

  const contentType = response.headers.get('content-type') || ''
  let data = null
  if (contentType.includes('application/json')) {
    try {
      data = await response.json()
    } catch (err) {
      logError('Invalid JSON response', path, err)
      throw new ApiError('Invalid JSON response from server', { status: response.status, path })
    }
  } else if (!allowEmpty) {
    data = {}
  }

  if (!response.ok) {
    const message =
      response.status === 502 || response.status === 503
        ? 'Backend unavailable — start API with ./scripts/dev.sh (port 8000)'
        : (apiDetail(data) || `HTTP ${response.status}`)
    logError('API error', response.status, path, message)
    throw new ApiError(message, { status: response.status, path, body: data })
  }

  return data
}

export async function apiGet(path, config) {
  return apiFetch(path, { method: 'GET' }, config)
}

export async function apiPost(path, body, config) {
  return apiFetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }, config)
}

export async function apiPatch(path, body, config) {
  return apiFetch(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }, config)
}

export async function apiDelete(path, config) {
  return apiFetch(path, { method: 'DELETE' }, config)
}

export function brokerStreamWsUrl() {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}/api/broker/stream/ws`
}

/** GET that returns null instead of throwing (for optional dashboard widgets). */
export async function apiGetOptional(path) {
  try {
    return await apiGet(path)
  } catch {
    return null
  }
}

/** POST JSON and return raw Response (for SSE streams). */
export async function apiPostStream(path, body) {
  logDebug('apiPostStream', path)
  let response
  try {
    response = await fetch(path, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        ...(getAuthToken() ? { Authorization: `Bearer ${getAuthToken()}` } : {}),
      },
      body: JSON.stringify(body),
    })
  } catch (err) {
    logError('Network error', path, err)
    throw new ApiError('Network error — is the backend running?', { path })
  }
  if (!response.ok) {
    const fail = await response.json().catch(() => ({}))
    const message = apiDetail(fail) || `HTTP ${response.status}`
    throw new ApiError(message, { status: response.status, path, body: fail })
  }
  return response
}

/** POST JSON and return a Blob (PDF exports, etc.). */
export async function apiPostBlob(path, body) {
  logDebug('apiPostBlob', path)
  let response
  try {
    response = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: '*/*' },
      body: JSON.stringify(body),
    })
  } catch (err) {
    logError('Network error', path, err)
    throw new ApiError('Network error — is the backend running?', { path })
  }
  if (!response.ok) {
    const fail = await response.json().catch(() => ({}))
    const message = apiDetail(fail) || `HTTP ${response.status}`
    throw new ApiError(message, { status: response.status, path, body: fail })
  }
  return response.blob()
}

/** POST multipart/form-data. */
export async function apiPostForm(path, formData) {
  logDebug('apiPostForm', path)
  let response
  try {
    response = await fetch(path, { method: 'POST', body: formData })
  } catch (err) {
    logError('Network error', path, err)
    throw new ApiError('Network error — is the backend running?', { path })
  }
  const contentType = response.headers.get('content-type') || ''
  let data = null
  if (contentType.includes('application/json')) {
    data = await response.json().catch(() => ({}))
  }
  if (!response.ok) {
    const message = apiDetail(data) || `HTTP ${response.status}`
    throw new ApiError(message, { status: response.status, path, body: data })
  }
  return data
}

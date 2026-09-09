/** Safe localStorage / sessionStorage helpers. */

import { logWarn } from './logger'

export function loadStore(key, fallback, { storage = localStorage } = {}) {
  try {
    const raw = storage.getItem(key)
    return raw ? JSON.parse(raw) : fallback
  } catch (err) {
    logWarn('loadStore failed', key, err)
    return fallback
  }
}

export function saveStore(key, value, { storage = localStorage } = {}) {
  try {
    storage.setItem(key, JSON.stringify(value))
    return true
  } catch (err) {
    logWarn('saveStore failed', key, err)
    return false
  }
}

export function removeStore(key, { storage = localStorage } = {}) {
  try {
    storage.removeItem(key)
    return true
  } catch (err) {
    logWarn('removeStore failed', key, err)
    return false
  }
}

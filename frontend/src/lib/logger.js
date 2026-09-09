/** Lightweight client logger — verbose in dev, quiet in production builds. */

const DEV = import.meta.env.DEV

export function logDebug(...args) {
  if (DEV) console.debug('[scan-bhav]', ...args)
}

export function logInfo(...args) {
  if (DEV) console.info('[scan-bhav]', ...args)
}

export function logWarn(...args) {
  console.warn('[scan-bhav]', ...args)
}

export function logError(...args) {
  console.error('[scan-bhav]', ...args)
}

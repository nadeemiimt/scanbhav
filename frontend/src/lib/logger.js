/** Lightweight client logger — verbose in dev, quiet in production builds. */

const DEV = import.meta.env.DEV

export function logDebug(...args) {
  if (DEV) console.debug('[stock-adda]', ...args)
}

export function logInfo(...args) {
  if (DEV) console.info('[stock-adda]', ...args)
}

export function logWarn(...args) {
  console.warn('[stock-adda]', ...args)
}

export function logError(...args) {
  console.error('[stock-adda]', ...args)
}

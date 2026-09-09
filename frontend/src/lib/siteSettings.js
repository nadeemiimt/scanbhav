export const SETTINGS_KEY = 'stockAddaSettings'

export const DEFAULT_SETTINGS = {
  theme: 'dark',
  skin: 'neo',
  beginnerMode: false,
  learnMode: false,
  provider: 'auto',
  forceRefresh: false,
  deskMode: 'mis',
}

function readLegacy() {
  return {
    beginnerMode: localStorage.getItem('stockAddaBeginner') === '1',
    learnMode: localStorage.getItem('stockAddaLearn') === '1',
  }
}

export function loadSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY)
    if (raw) {
      return { ...DEFAULT_SETTINGS, ...JSON.parse(raw), ...readLegacy() }
    }
  } catch {
    /* ignore */
  }
  return { ...DEFAULT_SETTINGS, ...readLegacy() }
}

export function applySettings(settings) {
  const root = document.documentElement
  root.setAttribute('data-theme', settings.theme || 'dark')
  root.setAttribute('data-skin', settings.skin || 'neo')
}

export function saveSettings(settings) {
  const merged = { ...DEFAULT_SETTINGS, ...settings }
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(merged))
  localStorage.setItem('stockAddaBeginner', merged.beginnerMode ? '1' : '0')
  localStorage.setItem('stockAddaLearn', merged.learnMode ? '1' : '0')
  applySettings(merged)
  return merged
}

export function resetSettings() {
  localStorage.removeItem(SETTINGS_KEY)
  const next = { ...DEFAULT_SETTINGS }
  saveSettings(next)
  return next
}

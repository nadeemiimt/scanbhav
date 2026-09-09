import { useEffect, useState } from 'react'
import { DEFAULT_SETTINGS, saveSettings, applySettings } from '../lib/siteSettings'
import { SECONDARY_NAV } from '../appNav'

const PROVIDERS = [
  { id: 'auto', label: 'Auto (Yahoo → NSE)' },
  { id: 'yfinance', label: 'Yahoo Finance' },
  { id: 'nse', label: 'NSE public data' },
]

function SettingsIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"
        stroke="currentColor"
        strokeWidth="1.75"
      />
      <path
        d="M19.4 13a7.8 7.8 0 0 0 .1-2l2-1.5-2-3.5-2.4 1a8 8 0 0 0-1.7-1L15 3h-4l-.4 2.5a8 8 0 0 0-1.7 1l-2.4-1-2 3.5 2 1.5a7.8 7.8 0 0 0 0 2l-2 1.5 2 3.5 2.4-1a8 8 0 0 0 1.7 1L11 21h4l.4-2.5a8 8 0 0 0 1.7-1l2.4 1 2-3.5-2-1.5Z"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function SettingsHeaderButton({ onClick, active }) {
  return (
    <button
      type="button"
      className={`ghost header-settings-btn${active ? ' is-active' : ''}`}
      onClick={onClick}
      aria-label="Website settings"
      title="Settings"
    >
      <SettingsIcon />
    </button>
  )
}

export function SettingsModal({
  open,
  onClose,
  settings,
  onChange,
  screenProviders,
  currentTab,
  onNavigate,
  onRerunWizard,
}) {
  const [draft, setDraft] = useState(settings)

  useEffect(() => {
    if (open) setDraft(settings)
  }, [open, settings])

  useEffect(() => {
    if (!open) return
    applySettings(draft)
  }, [draft, open])

  if (!open) return null

  function patch(partial) {
    setDraft(prev => ({ ...prev, ...partial }))
  }

  function apply() {
    const next = saveSettings(draft)
    onChange(next)
    onClose()
  }

  function cancel() {
    applySettings(settings)
    setDraft(settings)
    onClose()
  }

  function reset() {
    const next = { ...DEFAULT_SETTINGS }
    setDraft(next)
    saveSettings(next)
    onChange(next)
  }

  const providerOptions = screenProviders?.providers || PROVIDERS

  return (
    <div className="genai-modal-backdrop" role="dialog" aria-modal="true" aria-label="Website settings">
      <div className="genai-modal desk-tool-modal settings-modal">
        <section className="panel">
          <div className="panel-head">
            <div>
              <p className="eyebrow">SETTINGS</p>
              <h3>Website controls</h3>
            </div>
            <button type="button" className="ghost" onClick={cancel}>Close</button>
          </div>

          <div className="settings-modal-body">
            <section className="settings-section">
              <h4>More desks</h4>
              <p className="subtle settings-hint">
                Extra pages live here so the top bar stays compact on smaller screens.
              </p>
              <div className="settings-nav-grid">
                {SECONDARY_NAV.map(item => (
                  <button
                    key={item.id}
                    type="button"
                    className={`settings-nav-btn${currentTab === item.id ? ' is-active' : ''}`}
                    onClick={() => { onNavigate?.(item.id); onClose() }}
                  >
                    <span className="settings-nav-label">{item.label}</span>
                    {item.hint && <span className="settings-nav-hint">{item.hint}</span>}
                  </button>
                ))}
              </div>
            </section>

            <section className="settings-section">
              <h4>Desk mode</h4>
              <p className="subtle settings-hint">
                MIS Desk focuses on Autopilot execution. Full Research keeps every tab and horizon (PDF quant + research tools stay available).
              </p>
              <label className="settings-field">
                Navigation
                <select value={draft.deskMode || 'mis'} onChange={e => patch({ deskMode: e.target.value })}>
                  <option value="mis">MIS Desk — Autopilot first</option>
                  <option value="full">Full Research — all features</option>
                </select>
              </label>
            </section>

            <section className="settings-section">
              <h4>Appearance</h4>
              <label className="settings-field">
                Theme
                <select value={draft.theme} onChange={e => patch({ theme: e.target.value })}>
                  <option value="dark">Dark</option>
                  <option value="light">Light</option>
                </select>
              </label>
              <label className="settings-field">
                Skin
                <select value={draft.skin} onChange={e => patch({ skin: e.target.value })}>
                  <option value="neo">Neo terminal (default)</option>
                  <option value="classic">Classic gold desk</option>
                </select>
              </label>
              <p className="subtle settings-hint">Theme switches light/dark. Skin changes accent palette and header style.</p>
            </section>

            <section className="settings-section">
              <h4>Research display</h4>
              <label className="refresh-toggle settings-toggle">
                <input
                  type="checkbox"
                  checked={draft.beginnerMode}
                  onChange={e => patch({ beginnerMode: e.target.checked })}
                />
                Beginner mode — shorter copy, hide advanced panels
              </label>
              <label className="refresh-toggle settings-toggle">
                <input
                  type="checkbox"
                  checked={draft.learnMode}
                  onChange={e => patch({ learnMode: e.target.checked })}
                />
                Learn mode — tap metrics for explainers
              </label>
            </section>

            <section className="settings-section">
              <h4>Market data</h4>
              <label className="settings-field">
                Default data provider
                <select value={draft.provider} onChange={e => patch({ provider: e.target.value })}>
                  {providerOptions.map(p => (
                    <option key={p.id} value={p.id}>{p.label}</option>
                  ))}
                </select>
              </label>
              <label className="refresh-toggle settings-toggle">
                <input
                  type="checkbox"
                  checked={draft.forceRefresh}
                  onChange={e => patch({ forceRefresh: e.target.checked })}
                />
                Force refresh on Analyze / Swing scan (bypass cache)
              </label>
            </section>

            <section className="settings-section">
              <h4>Help</h4>
              <p className="subtle settings-hint">Walk through the desk features step by step.</p>
              <button
                type="button"
                className="primary settings-guide-btn"
                onClick={() => { onRerunWizard?.(); onClose() }}
              >
                Guide me
              </button>
            </section>

            <section className="settings-section">
              <h4>Other</h4>
              <div className="settings-actions-row">
                <button type="button" className="ghost" onClick={reset}>
                  Reset settings
                </button>
              </div>
            </section>
          </div>

          <div className="settings-modal-foot">
            <button type="button" className="ghost" onClick={cancel}>Cancel</button>
            <button type="button" className="primary" onClick={apply}>Save settings</button>
          </div>
        </section>
      </div>
    </div>
  )
}

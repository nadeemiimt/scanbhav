import { useEffect, useState } from 'react'
import { apiGet, apiPost } from '../lib/apiClient'

export function SetupPrereqsPanel({ compact = false, onDismiss }) {
  const [status, setStatus] = useState(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  async function load() {
    const data = await apiGet('/api/setup/status')
    setStatus(data)
  }

  useEffect(() => {
    load().catch(err => setMessage(err.message))
  }, [])

  async function installOllama() {
    setBusy(true)
    setMessage('')
    try {
      const res = await apiPost('/api/setup/install-ollama', { prefer_package_manager: true })
      setMessage(res.hint || (res.method === 'download_page' ? 'Opened the Ollama download page.' : 'Ollama install started.'))
      await load()
    } catch (err) {
      setMessage(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function openVc() {
    setBusy(true)
    try {
      await apiPost('/api/setup/open-vc-redist', {})
      setMessage('Opened the Visual C++ Redistributable download.')
    } catch (err) {
      setMessage(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function dismiss() {
    try {
      await apiPost('/api/setup/seen', {})
    } catch {
      /* ignore */
    }
    onDismiss?.()
  }

  if (!status) {
    return <p className="subtle">Checking what this computer needs…</p>
  }

  return (
    <section className={`settings-section${compact ? ' setup-compact' : ''}`}>
      <h4>Run on this computer</h4>
      <p className="settings-hint"><strong>{status.headline}</strong></p>
      <p className="subtle">Data folder: {status.data_dir}</p>

      <div className="token-guide-block">
        <p className="eyebrow">Required</p>
        <ul className="subtle">
          {(status.required || []).map(row => (
            <li key={row.id}>
              {row.ok ? '✓' : '○'} <b>{row.label}</b> — {row.plain}
            </li>
          ))}
        </ul>
      </div>

      <div className="token-guide-block">
        <p className="eyebrow">Optional — set up from here</p>
        <ul className="subtle">
          {(status.optional || []).map(row => (
            <li key={row.id}>
              {row.ok ? '✓' : '○'} <b>{row.label}</b> — {row.plain}
            </li>
          ))}
        </ul>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
          <button type="button" className="primary" disabled={busy || status.ollama?.ok} onClick={installOllama}>
            {status.ollama?.ok ? 'Ollama ready' : (busy ? 'Working…' : 'Install / open Ollama')}
          </button>
          {status.platform === 'win32' && (
            <button type="button" className="ghost" disabled={busy} onClick={openVc}>
              Get VC++ Redistributable
            </button>
          )}
          <button type="button" className="ghost" disabled={busy} onClick={() => load().catch(e => setMessage(e.message))}>
            Refresh checks
          </button>
          {onDismiss && (
            <button type="button" className="ghost" onClick={dismiss}>Got it</button>
          )}
        </div>
      </div>

      {(status.os_notes || []).length > 0 && (
        <div className="token-guide-block">
          <p className="eyebrow">OS notes</p>
          <ul className="subtle">
            {status.os_notes.map(note => <li key={note.slice(0, 40)}>{note}</li>)}
          </ul>
        </div>
      )}
      {message && <p className="subtle">{message}</p>}
    </section>
  )
}

export function FirstRunSetupModal({ open, onClose }) {
  if (!open) return null
  return (
    <div className="genai-modal-backdrop" role="dialog" aria-modal="true" aria-label="First-run setup">
      <div className="genai-modal desk-tool-modal settings-modal">
        <section className="panel">
          <div className="panel-head">
            <div>
              <p className="eyebrow">WELCOME</p>
              <h3>Before you share / first launch</h3>
            </div>
            <button type="button" className="ghost" onClick={onClose}>Close</button>
          </div>
          <SetupPrereqsPanel compact onDismiss={onClose} />
        </section>
      </div>
    </div>
  )
}

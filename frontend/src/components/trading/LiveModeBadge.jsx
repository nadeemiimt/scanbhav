import { useCallback, useEffect, useState } from 'react'
import { apiGet } from '../../lib/apiClient'

/** Global PAPER / LIVE + token health badge for site header. */
export function LiveModeBadge() {
  const [health, setHealth] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const h = await apiGet('/api/trading/health')
      setHealth(h)
    } catch {
      setHealth(null)
    }
  }, [])

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 30000)
    return () => clearInterval(t)
  }, [refresh])

  if (!health) return null

  const mode = health.execution_mode === 'live' && health.live_armed ? 'LIVE' : 'PAPER'
  const cls = mode === 'LIVE' ? 'live-mode-badge live' : 'live-mode-badge paper'
  const tokenOk = health.checks?.token_valid
  const ready = health.ready_for_live

  return (
    <span className={cls} title={health.halt_reason || health.token?.message || ''}>
      {mode}
      {mode === 'LIVE' && ready ? ' · ready' : ''}
      {mode === 'LIVE' && !tokenOk ? ' · token?' : ''}
      {health.halted ? ' · HALTED' : ''}
    </span>
  )
}

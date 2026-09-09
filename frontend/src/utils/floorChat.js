/** Live Research Desk floor chat timing + annotation helpers. */

export function formatTaskWhen(value) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  })
}

export function formatTook(ms) {
  if (ms == null || Number.isNaN(ms) || ms < 0) return null
  if (ms < 1000) return `${Math.round(ms)} ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`
  const mins = Math.floor(ms / 60_000)
  const secs = Math.round((ms % 60_000) / 1000)
  return `${mins}m ${secs}s`
}

/** Dwell time so Live Research Desk chat is readable before the next bubble. */
export function floorChatDelayMs(text, type) {
  const len = String(text || '').trim().length
  const readMs = Math.round((len / 16) * 1000)
  const base =
    type === 'handoff' ? 1500
      : type === 'status' ? 1200
        : type === 'briefcase' || type === 'done' ? 1100
          : 1800
  return Math.min(5200, Math.max(base, readMs))
}

function taskLabelFor(type) {
  switch (type) {
    case 'status': return 'Working'
    case 'handoff': return 'Handoff'
    case 'say': return 'Update'
    case 'briefcase': return 'Result filed'
    case 'done': return 'Complete'
    case 'error': return 'Error'
    default: return 'Task'
  }
}

export function annotateFloorMessages(messages) {
  const chrono = [...(messages || [])].sort((a, b) => {
    const ta = new Date(a.ts || a.receivedAt || 0).getTime()
    const tb = new Date(b.ts || b.receivedAt || 0).getTime()
    return ta - tb
  })
  if (!chrono.length) return []
  const startMs = new Date(chrono[0].ts || chrono[0].receivedAt).getTime()
  const agentStarted = {}
  const annotated = chrono.map((msg, index) => {
    const when = msg.ts || msg.receivedAt
    const t = new Date(when).getTime()
    const prev = index > 0 ? chrono[index - 1] : null
    const prevT = prev ? new Date(prev.ts || prev.receivedAt).getTime() : t
    const stepMs = index === 0 ? 0 : Math.max(0, t - prevT)
    let taskTookMs = null
    const agentId = msg.agent?.id
    if (msg.type === 'status' && agentId) {
      agentStarted[agentId] = t
    }
    if (agentId && agentStarted[agentId] != null && (msg.type === 'say' || msg.type === 'briefcase' || msg.type === 'error')) {
      taskTookMs = Math.max(0, t - agentStarted[agentId])
      delete agentStarted[agentId]
    } else if (msg.type === 'handoff' && agentId && agentStarted[agentId] != null) {
      taskTookMs = Math.max(0, t - agentStarted[agentId])
    } else if (msg.type === 'status') {
      taskTookMs = null
    } else if (stepMs > 0) {
      taskTookMs = stepMs
    }
    return {
      ...msg,
      when,
      taskLabel: taskLabelFor(msg.type),
      elapsedFromStartMs: Math.max(0, t - startMs),
      stepMs,
      taskTookMs,
    }
  })
  // Latest task on top
  return annotated.reverse()
}

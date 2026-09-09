import { useEffect, useMemo, useRef, useState } from 'react'
import { PlatformLimitationsPanel } from '../analysis/PlatformLimitations'
import { annotateFloorMessages, floorChatDelayMs, formatTaskWhen, formatTook } from '../../utils/floorChat'
import { number, pretty } from '../../utils/analysisFormatters'

const AGENT_SCENES = {
  lead: {
    caption: 'Orchestrating handoffs from the command desk',
    label: 'Desk command',
    activity: 'Routing tasks across the research floor',
  },
  tech: {
    caption: 'Reading candles, RSI, and horizon grades on the chart wall',
    label: 'Chart pit',
    activity: 'Scanning price action & indicator stack',
  },
  psych: {
    caption: 'Reading crowd mood — FOMO, fear, anchoring, and bias on the tape',
    label: 'Behavior lab',
    activity: 'Mapping trader psychology & bias flags',
  },
  forums: {
    caption: 'Sweeping Reddit, ValuePickr, and Traderji for forum chatter',
    label: 'Forum scout',
    activity: 'Collecting community threads & rumors',
  },
  news: {
    caption: 'In the field — scanning wires for war, supply, and rate shocks',
    label: 'Field scout',
    activity: 'Monitoring headlines & macro wires',
  },
  memory: {
    caption: 'Pulling prior memos and book passages from the vault',
    label: 'Insight library',
    activity: 'Retrieving vault memos & book passages',
  },
  writer: {
    caption: 'At the keyboard — drafting the research memo from facts only',
    label: 'Writer desk',
    activity: 'Drafting executive memo from desk facts',
  },
  clerk: {
    caption: 'Stamping and packing your result file into the briefcase',
    label: 'File room',
    activity: 'Filing stamped brief into briefcase',
  },
}

function formatDeskTimer(ms) {
  if (!ms || ms < 0) return '00:00.0'
  const totalSec = ms / 1000
  const mins = Math.floor(totalSec / 60)
  const secs = totalSec % 60
  return `${String(mins).padStart(2, '0')}:${secs.toFixed(1).padStart(4, '0')}`
}

function safeFileName(value) {
  return (value || 'desk').replace(/[^a-zA-Z0-9._-]+/g, '_').slice(0, 60)
}

function AgentPortrait({ agent, sceneId, live }) {
  return (
    <div className={`agent-portrait scene-${sceneId} ${live ? 'live' : ''}`} aria-hidden>
      <div className="agent-portrait-frame">
        <div className="agent-portrait-photo" style={{ '--agent-accent': agent?.accent || '#7eb8c4' }}>
          <div className="portrait-hair" />
          <div className="portrait-face">
            <div className="portrait-eyes">
              <span /><span />
            </div>
            <div className="portrait-smile" />
          </div>
          <div className="portrait-shoulders" />
          <span className="portrait-initials">{agent?.initials || '?'}</span>
        </div>
        {live && <span className="portrait-rec-dot">REC</span>}
      </div>
      <p className="portrait-name">{agent?.name || 'Desk'}</p>
      <p className="portrait-role">{agent?.role || 'Specialist'}</p>
    </div>
  )
}

function MonitorActivityBars({ sceneId, live }) {
  const bars = sceneId === 'tech' ? [40, 65, 52, 78, 61, 88, 70]
    : sceneId === 'forums' ? [55, 48, 62, 44, 58, 50, 66]
    : sceneId === 'news' ? [35, 42, 38, 55, 48, 60, 52]
    : [50, 58, 46, 64, 55, 72, 60]
  return (
    <div className={`monitor-activity-bars ${live ? 'live' : ''}`} aria-hidden>
      {bars.map((h, i) => (
        <span key={i} className="monitor-bar" style={{ '--h': `${h}%`, animationDelay: `${i * 0.08}s` }} />
      ))}
    </div>
  )
}

function AgentWorkStage({
  agentId, agent, busy, symbol, currentTask, deskElapsedMs, taskCount, progressPct, compact = false,
}) {
  const sceneId = agentId || 'lead'
  const meta = AGENT_SCENES[sceneId] || AGENT_SCENES.lead
  const accent = agent?.accent || '#7eb8c4'
  const live = busy
  const taskText = currentTask?.text
    ? (currentTask.text.length > 180 ? `${currentTask.text.slice(0, 177)}…` : currentTask.text)
    : (live ? meta.activity : 'Standing by for the next handoff')
  const taskLabel = currentTask?.taskLabel || (live ? 'IN PROGRESS' : 'STANDBY')

  return (
    <div
      className={`agent-stage agent-monitor scene-${sceneId} ${live ? 'live' : 'idle'} ${compact ? 'compact' : ''}`}
      style={{ '--agent-accent': accent }}
      aria-live={live ? 'polite' : 'off'}
    >
      <div className="agent-monitor-hud">
        <div className="monitor-hud-left">
          {live && <span className="stage-live-pill">● LIVE</span>}
          <span className="monitor-timer" aria-label="Desk elapsed time">
            <small>DESK</small>
            <strong>{formatDeskTimer(deskElapsedMs)}</strong>
          </span>
          {currentTask?.taskTookMs != null && currentTask.taskTookMs > 0 && (
            <span className="monitor-task-timer">
              <small>TASK</small>
              <strong>{formatTook(currentTask.taskTookMs)}</strong>
            </span>
          )}
        </div>
        <div className="monitor-hud-right">
          <span className="monitor-stat">{taskCount} task{taskCount === 1 ? '' : 's'}</span>
          {progressPct != null && (
            <span className="monitor-progress-wrap">
              <span className="monitor-progress-track">
                <span className="monitor-progress-fill" style={{ width: `${Math.round(progressPct * 100)}%` }} />
              </span>
              <span className="monitor-stat">{Math.round(progressPct * 100)}%</span>
            </span>
          )}
        </div>
      </div>

      <div className="agent-monitor-frame">
        <div className="agent-monitor-chrome">
          <span className="monitor-chrome-dots"><i /><i /><i /></span>
          <span className="monitor-chrome-title">{meta.label.toUpperCase()} · {symbol}</span>
          <span className="monitor-chrome-status">{live ? 'STREAMING' : 'IDLE'}</span>
        </div>
        <div className="agent-monitor-screen">
          <AgentPortrait agent={agent} sceneId={sceneId} live={live} />
          <div className="monitor-feed">
            <p className="monitor-feed-label">{taskLabel}</p>
            {currentTask?.type === 'handoff' && currentTask.toAgent && (
              <p className="monitor-handoff">→ {currentTask.toAgent.name}</p>
            )}
            <p className="monitor-feed-text">{taskText}</p>
            <MonitorActivityBars sceneId={sceneId} live={live} />
            {!compact && <p className="monitor-feed-caption">{meta.caption}</p>}
          </div>
        </div>
      </div>
    </div>
  )
}

function SceneWriter() {
  return (
    <svg className="work-scene" viewBox="0 0 280 140" role="img">
      <rect x="8" y="18" width="160" height="100" rx="4" className="sc-desk" />
      <rect x="28" y="28" width="120" height="72" rx="3" className="sc-screen" />
      <rect x="34" y="34" width="108" height="52" className="sc-screen-inner" />
      <g className="sc-type-lines">
        <rect x="40" y="40" width="70" height="3" className="sc-line a" />
        <rect x="40" y="48" width="88" height="3" className="sc-line b" />
        <rect x="40" y="56" width="54" height="3" className="sc-line c" />
        <rect x="40" y="64" width="76" height="3" className="sc-line d" />
        <rect x="40" y="72" width="40" height="3" className="sc-cursor" />
      </g>
      <rect x="70" y="102" width="36" height="6" className="sc-stand" />
      <ellipse cx="200" cy="108" rx="34" ry="8" className="sc-shadow" />
      <g className="sc-person typing">
        <circle cx="200" cy="42" r="14" className="sc-head" />
        <path d="M186 58 h28 l8 42 h-44 z" className="sc-body" />
        <path d="M188 72 L150 88" className="sc-arm left" />
        <path d="M212 72 L238 86" className="sc-arm right" />
      </g>
      <g className="sc-keys">
        <rect x="148" y="96" width="70" height="18" rx="2" className="sc-keyboard" />
        <rect x="154" y="100" width="8" height="5" className="sc-key k1" />
        <rect x="166" y="100" width="8" height="5" className="sc-key k2" />
        <rect x="178" y="100" width="8" height="5" className="sc-key k3" />
        <rect x="190" y="100" width="8" height="5" className="sc-key k4" />
      </g>
    </svg>
  )
}

function SceneTech() {
  return (
    <svg className="work-scene" viewBox="0 0 280 140" role="img">
      <rect x="20" y="20" width="150" height="90" rx="3" className="sc-screen wide" />
      <polyline className="sc-chart-line" points="36,88 56,70 76,76 96,48 116,58 136,36 156,44" />
      <g className="sc-candles">
        <rect x="48" y="60" width="6" height="22" className="sc-candle up" />
        <rect x="68" y="52" width="6" height="28" className="sc-candle down" />
        <rect x="88" y="40" width="6" height="34" className="sc-candle up" />
        <rect x="108" y="46" width="6" height="26" className="sc-candle up" />
        <rect x="128" y="34" width="6" height="36" className="sc-candle down" />
      </g>
      <ellipse cx="210" cy="112" rx="32" ry="7" className="sc-shadow" />
      <g className="sc-person pointing">
        <circle cx="210" cy="46" r="13" className="sc-head" />
        <path d="M198 60 h24 l7 40 h-38 z" className="sc-body" />
        <path d="M204 72 L160 58" className="sc-arm left point" />
        <path d="M220 74 L236 90" className="sc-arm right" />
      </g>
    </svg>
  )
}

function ScenePsych() {
  return (
    <svg className="work-scene" viewBox="0 0 280 140" role="img">
      <rect x="24" y="24" width="120" height="88" rx="6" className="sc-screen" />
      <path d="M40 88 Q70 52 100 88" className="sc-chart-line mood" />
      <circle cx="70" cy="62" r="10" className="sc-mood-ring" />
      <text x="66" y="66" fontSize="10" className="sc-mood-icon">?</text>
      <ellipse cx="210" cy="112" rx="32" ry="7" className="sc-shadow" />
      <g className="sc-person thinking">
        <circle cx="210" cy="46" r="13" className="sc-head" />
        <path d="M198 60 h24 l7 40 h-38 z" className="sc-body" />
        <path d="M204 68 L170 78" className="sc-arm left" />
        <path d="M220 68 L248 54" className="sc-arm right point" />
      </g>
    </svg>
  )
}

function SceneForums() {
  return (
    <svg className="work-scene" viewBox="0 0 280 140" role="img">
      <rect x="16" y="28" width="148" height="78" rx="4" className="sc-screen" />
      <g className="sc-forum-bubbles">
        <rect x="28" y="40" width="90" height="14" rx="3" className="sc-line a" />
        <rect x="28" y="58" width="110" height="14" rx="3" className="sc-line b" />
        <rect x="28" y="76" width="72" height="14" rx="3" className="sc-line c" />
        <rect x="108" y="76" width="44" height="14" rx="3" className="sc-line d" />
      </g>
      <ellipse cx="210" cy="112" rx="32" ry="7" className="sc-shadow" />
      <g className="sc-person scanning">
        <circle cx="210" cy="46" r="13" className="sc-head" />
        <path d="M198 60 h24 l7 40 h-38 z" className="sc-body" />
        <rect x="228" y="64" width="28" height="20" rx="2" className="sc-tablet" />
      </g>
    </svg>
  )
}

function SceneNewsField() {
  return (
    <svg className="work-scene" viewBox="0 0 280 140" role="img">
      <rect x="0" y="95" width="280" height="45" className="sc-ground" />
      <path d="M0 95 Q70 70 140 95 T280 90" className="sc-horizon" />
      <g className="sc-sun"><circle cx="240" cy="28" r="12" /></g>
      <g className="sc-person field">
        <circle cx="90" cy="52" r="12" className="sc-head" />
        <path d="M78 66 h24 l6 28 h-36 z" className="sc-body" />
        <path d="M82 78 L60 92" className="sc-arm left" />
        <path d="M106 76 L128 70" className="sc-arm right notepad" />
        <rect x="124" y="58" width="28" height="22" rx="2" className="sc-notepad" />
        <line x1="130" y1="64" x2="146" y2="64" className="sc-note-line a" />
        <line x1="130" y1="70" x2="144" y2="70" className="sc-note-line b" />
        <line x1="130" y1="76" x2="142" y2="76" className="sc-note-line c" />
        <path d="M84 94 L78 112 M96 94 L102 112" className="sc-legs" />
      </g>
      <g className="sc-radio">
        <rect x="175" y="78" width="42" height="22" rx="3" className="sc-radio-box" />
        <circle cx="196" cy="89" r="6" className="sc-radio-dial" />
        <g className="sc-waves">
          <path d="M222 82 q12 8 0 16" />
          <path d="M230 76 q18 14 0 28" />
          <path d="M238 70 q24 20 0 40" />
        </g>
      </g>
      <g className="sc-papers">
        <rect x="40" y="30" width="36" height="22" className="sc-paper p1" />
        <rect x="150" y="24" width="32" height="20" className="sc-paper p2" />
      </g>
    </svg>
  )
}

function SceneLibrary() {
  return (
    <svg className="work-scene" viewBox="0 0 280 140" role="img">
      <rect x="20" y="20" width="120" height="100" className="sc-shelf" />
      <g className="sc-books">
        <rect x="28" y="28" width="12" height="36" className="sc-book b1" />
        <rect x="44" y="32" width="10" height="32" className="sc-book b2" />
        <rect x="58" y="26" width="14" height="38" className="sc-book b3 pull" />
        <rect x="78" y="30" width="11" height="34" className="sc-book b4" />
        <rect x="94" y="28" width="13" height="36" className="sc-book b5" />
        <rect x="30" y="72" width="100" height="8" className="sc-shelf-plank" />
        <rect x="34" y="84" width="11" height="28" className="sc-book b6" />
        <rect x="50" y="88" width="14" height="24" className="sc-book b7 glow" />
        <rect x="70" y="86" width="10" height="26" className="sc-book b8" />
      </g>
      <ellipse cx="200" cy="114" rx="30" ry="7" className="sc-shadow" />
      <g className="sc-person librarian">
        <circle cx="200" cy="48" r="13" className="sc-head" />
        <path d="M188 62 h24 l6 38 h-36 z" className="sc-body" />
        <path d="M192 74 L150 58" className="sc-arm left reach" />
        <path d="M216 76 L236 92" className="sc-arm right" />
      </g>
      <circle cx="152" cy="54" r="10" className="sc-vault-glow" />
    </svg>
  )
}

function SceneBriefcase() {
  return (
    <svg className="work-scene" viewBox="0 0 280 140" role="img">
      <rect x="30" y="70" width="120" height="40" className="sc-table" />
      <g className="sc-case-anim">
        <rect x="58" y="58" width="64" height="40" rx="3" className="sc-case-body" />
        <path d="M58 58 h64 v-14 h-64 z" className="sc-case-lid open-lid" />
        <rect x="84" y="42" width="12" height="8" className="sc-case-handle" />
        <rect x="72" y="68" width="36" height="22" className="sc-file slip" />
      </g>
      <ellipse cx="200" cy="112" rx="28" ry="7" className="sc-shadow" />
      <g className="sc-person clerk">
        <circle cx="200" cy="46" r="13" className="sc-head" />
        <path d="M188 60 h24 l6 40 h-36 z" className="sc-body" />
        <path d="M192 74 L140 78" className="sc-arm left stamp" />
        <path d="M216 74 L236 88" className="sc-arm right" />
      </g>
      <circle cx="118" cy="78" r="8" className="sc-stamp" />
    </svg>
  )
}

function SceneLead() {
  return (
    <svg className="work-scene" viewBox="0 0 280 140" role="img">
      <rect x="18" y="24" width="90" height="58" rx="3" className="sc-board" />
      <circle cx="40" cy="42" r="6" className="sc-dot a" />
      <circle cx="62" cy="42" r="6" className="sc-dot b" />
      <circle cx="84" cy="42" r="6" className="sc-dot c" />
      <path d="M40 48 L62 48 L84 48" className="sc-links" />
      <rect x="130" y="78" width="100" height="28" className="sc-lead-desk" />
      <ellipse cx="180" cy="112" rx="34" ry="7" className="sc-shadow" />
      <g className="sc-person lead">
        <circle cx="180" cy="44" r="14" className="sc-head" />
        <path d="M166 60 h28 l8 42 h-44 z" className="sc-body" />
        <path d="M172 72 L120 58" className="sc-arm left point" />
        <path d="M192 74 L230 70" className="sc-arm right wave" />
      </g>
      <path d="M210 36 q8 -10 16 0" className="sc-headset" />
    </svg>
  )
}

function formatForecastWhen(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString(undefined, {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return iso
  }
}

function formatPct(value, digits = 2) {
  if (value == null || Number.isNaN(Number(value))) return '—'
  const n = Number(value)
  return `${n > 0 ? '+' : ''}${n.toFixed(digits)}%`
}

export function ForecastTablePanel({ table, insight }) {
  const fc = insight?.forecast_7d || table?.latest || {}
  const runs = table?.runs || []
  const forward = table?.forward_path || []
  if (!fc?.target_price && !runs.length) return null

  return (
    <>
      <h4>7-day scenario forecast</h4>
      <p className="subtle">
        Timestamped runs in RAG — rerun same day to see intraday drift (Morning vs Afternoon).
      </p>

      {runs.length > 0 && (
        <>
          <h5 className="forecast-subhead">Forecast runs (date &amp; time)</h5>
          <div className="table-wrap forecast-table-wrap">
            <table className="forecast-table">
              <thead>
                <tr>
                  <th>Recorded</th>
                  <th>Session</th>
                  <th>Baseline</th>
                  <th>Dir</th>
                  <th>Target</th>
                  <th>Exp %</th>
                  <th>Drift</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((row, i) => (
                  <tr key={row.id || i} className={row.drift_highlight ? 'forecast-drift-row' : ''}>
                    <td>{formatForecastWhen(row.recorded_at)}</td>
                    <td>{row.session || '—'}</td>
                    <td>{row.baseline_price ?? '—'}</td>
                    <td>{pretty(row.direction)}</td>
                    <td>{row.target_price ?? '—'}</td>
                    <td>{formatPct(row.expected_return_pct)}</td>
                    <td className={row.drift_highlight ? 'drift-hit' : ''}>
                      {row.drift?.target_drift_pct != null
                        ? formatPct(row.drift.target_drift_pct)
                        : '—'}
                    </td>
                    <td className={row.drift_highlight ? 'drift-reason' : 'subtle'}>
                      {row.drift_reason || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {forward.length > 0 && (
        <>
          <h5 className="forecast-subhead">Next 7 days — scenario path</h5>
          <div className="table-wrap forecast-table-wrap">
            <table className="forecast-table forward-table">
              <thead>
                <tr>
                  <th>Day</th>
                  <th>Date</th>
                  <th>Path mid</th>
                  <th>Band low</th>
                  <th>Band high</th>
                </tr>
              </thead>
              <tbody>
                {forward.map(row => (
                  <tr key={row.day_offset}>
                    <td>D+{row.day_offset}</td>
                    <td>{row.label || row.date}</td>
                    <td>{row.path_mid}</td>
                    <td>{row.path_low}</td>
                    <td>{row.path_high}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {fc.rationale && <p className="forecast-rationale">{fc.rationale}</p>}
    </>
  )
}

export function GenaiResearchPanel({
  symbol, providers, provider, setProvider, model, setModel, busy, result, onRun,
  messages, roster, progress, floorTab, setFloorTab, briefcaseOpen, activeSpeaker,
  executeTrades = false, setExecuteTrades, tradeQuantity = 1, setTradeQuantity,
  autonomousPicks = false, setAutonomousPicks, maxAutonomousPicks = 1, setMaxAutonomousPicks,
  modal = false, onClose,
}) {
  const catalog = providers?.providers || []
  const configured = providers?.configured || {}
  const active = catalog.find(p => p.id === provider) || catalog[0]
  const models = active?.models || []
  const keyMissing = (
    (provider === 'cursor' && !configured.cursor_api_key)
    || (provider === 'openai' && !configured.openai_api_key)
    || (provider === 'openai_compatible' && !configured.openai_api_key)
    || (provider === 'anthropic' && !configured.anthropic_api_key)
  )
  const floorRef = useRef(null)
  const briefcaseExportRef = useRef(null)
  const deskStartRef = useRef(null)
  const [tick, setTick] = useState(0)
  const [pdfBusy, setPdfBusy] = useState(false)
  const defaultRoster = roster?.length ? roster : [
    { id: 'lead', name: 'Arjun Mehta', role: 'Desk Lead', initials: 'AM', accent: '#e8b84a' },
    { id: 'tech', name: 'Naina Kapoor', role: 'Technical Analyst', initials: 'NK', accent: '#2ecf8a' },
    { id: 'psych', name: 'Dr. Ananya Rao', role: 'Market Psychologist', initials: 'AR', accent: '#e8a4c8' },
    { id: 'forums', name: 'Kabir Malhotra', role: 'Forum Scout', initials: 'KM', accent: '#7ec8e3' },
    { id: 'news', name: 'Vikram Sethi', role: 'News & Macro Scout', initials: 'VS', accent: '#f07178' },
    { id: 'memory', name: 'Meera Iyer', role: 'Memory Librarian', initials: 'MI', accent: '#9ec3e8' },
    { id: 'writer', name: 'Rohan Desai', role: 'Research Writer', initials: 'RD', accent: '#c6b6e8' },
    { id: 'clerk', name: 'Sara Almeida', role: 'Briefcase Clerk', initials: 'SA', accent: '#e8b84a' },
  ]

  useEffect(() => {
    if (!models.length) return
    if (!models.some(m => m.id === model)) setModel(models[0].id)
  }, [provider, models, model, setModel])

  const floorTasks = useMemo(() => annotateFloorMessages(messages), [messages])
  const spokenAgentIds = useMemo(() => {
    const ids = new Set()
    floorTasks.forEach(msg => {
      if (msg.agent?.id) ids.add(msg.agent.id)
      if (msg.toAgent?.id) ids.add(msg.toAgent.id)
    })
    return ids
  }, [floorTasks])
  const deskTook = floorTasks.length
    ? formatTook(Math.max(...floorTasks.map(m => m.elapsedFromStartMs || 0)))
    : null

  useEffect(() => {
    if (busy && !deskStartRef.current) deskStartRef.current = Date.now()
    if (!busy) deskStartRef.current = null
  }, [busy])

  useEffect(() => {
    if (!busy) return undefined
    const id = setInterval(() => setTick(t => t + 1), 100)
    return () => clearInterval(id)
  }, [busy])

  const deskElapsedMs = useMemo(() => {
    if (floorTasks.length) {
      return Math.max(...floorTasks.map(m => m.elapsedFromStartMs || 0))
    }
    if (busy && deskStartRef.current) {
      return Date.now() - deskStartRef.current
    }
    return 0
  }, [floorTasks, busy, tick])

  const currentTask = useMemo(() => {
    if (!floorTasks.length) return null
    if (activeSpeaker) {
      return floorTasks.find(m => m.agent?.id === activeSpeaker) || floorTasks[0]
    }
    return floorTasks[0]
  }, [floorTasks, activeSpeaker])

  useEffect(() => {
    // Latest on top — keep viewport pinned to newest tasks
    if (floorRef.current) floorRef.current.scrollTop = 0
  }, [floorTasks.length, floorTab])

  const insight = result?.insight
  const hasBrief = Boolean(insight)
  const stageAgentId = activeSpeaker || floorTasks[0]?.agent?.id || null

  async function downloadBriefcasePdf() {
    const el = briefcaseExportRef.current
    if (!el || !hasBrief) return
    setPdfBusy(true)
    const prevOverflow = el.style.overflow
    const prevMaxHeight = el.style.maxHeight
    const prevHeight = el.style.height
    el.style.overflow = 'visible'
    el.style.maxHeight = 'none'
    el.style.height = 'auto'
    try {
      const { default: html2pdf } = await import('html2pdf.js')
      await html2pdf().set({
        margin: [10, 10, 12, 10],
        filename: `${safeFileName(symbol)}_research_brief.pdf`,
        image: { type: 'jpeg', quality: 0.98 },
        html2canvas: {
          scale: 2,
          useCORS: true,
          backgroundColor: '#071018',
          logging: false,
          scrollX: 0,
          scrollY: -window.scrollY,
          windowWidth: el.scrollWidth,
          width: el.scrollWidth,
          height: el.scrollHeight,
        },
        jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
        pagebreak: { mode: ['css', 'legacy'], avoid: ['.forecast-review-row', 'tr'] },
      }).from(el).save()
    } catch (err) {
      console.error(err)
    } finally {
      el.style.overflow = prevOverflow
      el.style.maxHeight = prevMaxHeight
      el.style.height = prevHeight
      setPdfBusy(false)
    }
  }

  return (
    <section className={`panel genai-panel agent-floor-panel ${modal ? 'in-modal' : ''}`}>
      <div className="panel-head">
        <div>
          <p className="eyebrow">LIVE RESEARCH DESK</p>
          <h3>Live desk · {symbol}</h3>
        </div>
        <div className="panel-head-actions">
          <div className={`briefcase-badge ${briefcaseOpen || hasBrief ? 'ready' : ''} ${briefcaseOpen ? 'pop' : ''}`}>
            <span className="briefcase-lid" aria-hidden />
            <span>{hasBrief ? 'Briefcase ready' : 'Briefcase empty'}</span>
          </div>
          {modal && onClose && (
            <button type="button" className="ghost" onClick={onClose}>Close</button>
          )}
        </div>
      </div>

      <p className="subtle desk-lede">
        Eight specialists · live handoffs · briefcase filing
      </p>

      <PlatformLimitationsPanel compact />

      <div className="desk-controls">
        <label>
          Provider
          <select value={provider} onChange={e => setProvider(e.target.value)}>
            {catalog.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
          </select>
        </label>
        <label>
          Model
          <select value={model} onChange={e => setModel(e.target.value)}>
            {models.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
          </select>
        </label>
        {setExecuteTrades && (
          <label className="refresh-toggle desk-trade-toggle" title="Routes via /api/broker/order — paper or live per Autopilot desk">
            <input
              type="checkbox"
              checked={executeTrades}
              onChange={e => setExecuteTrades(e.target.checked)}
            />
            Execute trades (paper/live)
          </label>
        )}
        {setAutonomousPicks && (
          <label
            className="refresh-toggle desk-trade-toggle"
            title="ON: pick best names from full Nifty 500 within budget. OFF: trade only your Autopilot watchlist + desk symbol."
          >
            <input
              type="checkbox"
              checked={autonomousPicks}
              onChange={e => setAutonomousPicks(e.target.checked)}
            />
            Auto-pick from Nifty 500
          </label>
        )}
        {autonomousPicks && (
          <p className="subtle desk-trade-hint">Scans all 500 (morning RAG) · sizes to budget · max profit</p>
        )}
        {!autonomousPicks && executeTrades && (
          <p className="subtle desk-trade-hint">Trades your watchlist + current symbol only</p>
        )}
        {setMaxAutonomousPicks && autonomousPicks && (
          <label>
            Max picks
            <input
              type="number"
              min={1}
              max={3}
              value={maxAutonomousPicks}
              onChange={e => setMaxAutonomousPicks(Math.min(3, Math.max(1, Number(e.target.value) || 1)))}
              style={{ width: 48 }}
            />
          </label>
        )}
        {setTradeQuantity && executeTrades && autonomousPicks && (
          <label title="Max shares per pick (optional cap; qty also limited by Autopilot risk caps)">
            Max qty/pick
            <input
              type="number"
              min={1}
              max={1000}
              value={tradeQuantity}
              onChange={e => setTradeQuantity(Math.max(1, Number(e.target.value) || 1))}
              style={{ width: 64 }}
            />
          </label>
        )}
        {setTradeQuantity && executeTrades && !autonomousPicks && (
          <label>
            Qty
            <input
              type="number"
              min={1}
              max={1000}
              value={tradeQuantity}
              onChange={e => setTradeQuantity(Math.max(1, Number(e.target.value) || 1))}
              style={{ width: 64 }}
            />
          </label>
        )}
        <button type="button" className="primary" disabled={busy || keyMissing} onClick={onRun}>
          {busy ? 'Desk is live…' : hasBrief ? 'Run the desk again' : 'Call the research desk'}
        </button>
      </div>
      {keyMissing && (
        <p className="error" style={{ marginTop: 10 }}>
          {provider === 'cursor'
            ? 'CURSOR_API_KEY is not set in .env — switch to Ollama (local) or add your Cursor API key.'
            : `Missing API key for ${provider}. Check .env (${active?.key_env || 'API key'}) or use Ollama.`}
        </p>
      )}
      {result?.runError && <p className="error" style={{ marginTop: 10 }}>{result.runError}</p>}
      {autonomousPicks && !executeTrades && (
        <p className="subtle" style={{ marginTop: 8 }}>
          Autonomous scan only — enable Execute trades to place orders on top picks.
        </p>
      )}
      {result?.agent_picks && (
        <div className="agent-picks-panel" style={{ marginTop: 10 }}>
          <p className="eyebrow">AUTONOMOUS PICKS</p>
          {(result.agent_picks.picks || []).length === 0 && (
            <p className="subtle">No names passed composite/stance filters ({result.agent_picks.scanned_count} scanned).</p>
          )}
          <ul className="reason-list compact">
            {(result.agent_picks.picks || []).map(p => (
              <li key={p.symbol}>
                <strong>{p.symbol}</strong> qty {p.quantity} · ₹{p.notional_inr?.toLocaleString('en-IN')}
                {' · '}est. profit ₹{p.expected_profit_inr}
                {' · '}composite {p.composite_score} · {p.stance}
                {p.fit_reason && ` — ${p.fit_reason}`}
              </li>
            ))}
          </ul>
          {result.agent_picks.budget && (
            <p className="subtle">
              Budget: ₹{result.agent_picks.budget.remaining_budget_inr?.toLocaleString('en-IN')} remaining of
              ₹{result.agent_picks.budget.max_daily_notional_inr?.toLocaleString('en-IN')} daily ·
              ₹{result.agent_picks.budget.max_per_order_inr?.toLocaleString('en-IN')}/order cap
            </p>
          )}
          {(result.agent_picks.trades || []).length > 0 && (
            <p className="subtle" style={{ marginTop: 6 }}>
              Trades: {(result.agent_picks.trades || []).map(t => (
                `${t.symbol}${t.skipped ? ` (skipped: ${t.reason})` : ` (${t.mode || 'paper'})`}`
              )).join(' · ')}
            </p>
          )}
        </div>
      )}
      {result?.agent_trade && !result?.agent_picks && (
        <p className="subtle" style={{ marginTop: 8 }}>
          Agent trade: {result.agent_trade.skipped ? `skipped (${result.agent_trade.reason})` : JSON.stringify(result.agent_trade)}
        </p>
      )}

      <div className="agent-roster" aria-label="Research desk specialists">
        {defaultRoster.map(agent => {
          const speaking = activeSpeaker === agent.id
          const done = spokenAgentIds.has(agent.id) && !speaking
          return (
            <div
              key={agent.id}
              className={`agent-chip ${speaking ? 'speaking' : ''} ${done ? 'done' : ''}`}
              style={{ '--agent-accent': agent.accent }}
            >
              <span className="agent-avatar">{agent.initials}</span>
              <span>
                <strong>{agent.name}</strong>
                <small>{speaking ? 'On floor now' : done ? 'Handoff complete' : agent.role}</small>
              </span>
              {speaking && <span className="agent-live-dot" aria-hidden />}
            </div>
          )
        })}
      </div>

      {(busy || progress > 0) && (
        <div className="agent-progress" aria-hidden>
          <div className="agent-progress-bar" style={{ width: `${Math.max(4, Math.round((progress || 0) * 100))}%` }} />
        </div>
      )}

      <div className="floor-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          className={floorTab === 'floor' ? 'active' : ''}
          aria-selected={floorTab === 'floor'}
          onClick={() => setFloorTab('floor')}
        >
          Research floor
        </button>
        <button
          type="button"
          role="tab"
          className={floorTab === 'briefcase' ? 'active' : ''}
          aria-selected={floorTab === 'briefcase'}
          onClick={() => setFloorTab('briefcase')}
          disabled={!hasBrief && !busy}
        >
          Briefcase / Result file
          {hasBrief ? <span className="tab-dot" /> : null}
        </button>
      </div>

      {floorTab === 'floor' && (
        <div className="desk-body">
          <AgentWorkStage
            agentId={stageAgentId}
            agent={(defaultRoster.find(a => a.id === stageAgentId) || null)}
            busy={busy || Boolean(activeSpeaker)}
            symbol={symbol}
            currentTask={currentTask}
            deskElapsedMs={deskElapsedMs}
            taskCount={floorTasks.length}
            progressPct={progress}
            compact={modal}
          />

          <section className="floor-transcript" aria-label="Research floor transcript">
            <div className="floor-transcript-head">
              <div>
                <p className="eyebrow">FLOOR TRANSCRIPT</p>
                <h4>Live handoffs &amp; chat</h4>
              </div>
              <div className="floor-transcript-actions">
                <span className="floor-transcript-meta">
                  {floorTasks.length} message{floorTasks.length === 1 ? '' : 's'}
                  {deskTook ? ` · ${deskTook}` : ''}
                </span>
              </div>
            </div>

            <div className="agent-floor floor-chat-scroll" ref={floorRef}>
          {busy && activeSpeaker && (
            <div className="typing-row top floor-chat-typing">
              <span className="typing-dot" />
              <span className="typing-dot" />
              <span className="typing-dot" />
              <span className="subtle">
                {(defaultRoster.find(a => a.id === activeSpeaker) || {}).name || 'Someone'} is working…
              </span>
            </div>
          )}
          {!floorTasks.length && !busy && (
            <div className="floor-empty">
              <p>The floor is quiet. Call the desk and Arjun will greet you, then hand work to Naina, Dr. Ananya, Kabir, Vikram, Meera, Rohan, and Sara.</p>
              {result?.from_cache && insight && (
                <p className="subtle">A prior memo is already in the Briefcase from Chroma — open that tab, or run the desk for a live update.</p>
              )}
            </div>
          )}
          {floorTasks.map((msg, idx) => (
            <article
              key={msg.id}
              className={`floor-chat-card speech-row type-${msg.type}`}
              style={{ animationDelay: `${Math.min(idx, 8) * 35}ms` }}
            >
              <div className="agent-avatar lg" style={{ '--agent-accent': msg.agent?.accent || '#e8b84a' }}>
                {msg.agent?.initials || '?'}
              </div>
              <div className="speech-bubble" style={{ borderLeftColor: msg.agent?.accent || undefined }}>
                <div className="task-timing">
                  <span className="task-label">{msg.taskLabel}</span>
                  <time dateTime={msg.when}>{formatTaskWhen(msg.when)}</time>
                  {msg.taskTookMs != null && msg.taskTookMs > 0 && (
                    <span className="task-took">took {formatTook(msg.taskTookMs)}</span>
                  )}
                  {msg.elapsedFromStartMs != null && (
                    <span className="task-elapsed">+{formatTook(msg.elapsedFromStartMs)} from start</span>
                  )}
                </div>
                <div className="speech-meta">
                  <strong>{msg.agent?.name || 'Desk'}</strong>
                  <span>{msg.agent?.role}</span>
                  {msg.type === 'handoff' && msg.toAgent && (
                    <span className="handoff-tag">→ {msg.toAgent.name}</span>
                  )}
                  {msg.type === 'status' && <span className="working-tag">working</span>}
                  {msg.speakingTo && msg.speakingTo !== 'you' && msg.type === 'say' && (
                    <span className="subtle">to {msg.speakingTo}</span>
                  )}
                  {msg.speakingTo === 'you' && msg.type === 'say' && (
                    <span className="to-you">to you</span>
                  )}
                </div>
                <p className="floor-chat-text">{msg.text}</p>
              </div>
            </article>
          ))}
            </div>
          </section>
        </div>
      )}

      {floorTab === 'briefcase' && (
        <div className={`desk-body`}>
        <div className={`briefcase-panel briefcase-pdf-root ${briefcaseOpen ? 'opening' : ''}`} ref={briefcaseExportRef}>
          <div className="briefcase-header">
            <div className={`briefcase-icon ${briefcaseOpen || hasBrief ? 'open' : ''}`} aria-hidden>
              <span className="case-body" />
              <span className="case-lid" />
            </div>
            <div className="briefcase-header-copy">
              <p className="eyebrow">{result?.briefcase?.label || 'RESULT FILE'}</p>
              <h4>{result?.briefcase?.title || `${symbol} research brief`}</h4>
              <p className="subtle">
                {result?.briefcase?.filed_at
                  ? `Filed ${new Date(result.briefcase.filed_at).toLocaleString()}`
                  : result?.from_cache
                    ? 'Loaded from Chroma vault'
                    : 'Awaiting filing'}
                {result?.provider ? ` · ${result.provider} / ${result.model}` : ''}
              </p>
            </div>
            {insight && (
              <button
                type="button"
                className="ghost briefcase-pdf-btn"
                disabled={pdfBusy}
                onClick={downloadBriefcasePdf}
                data-html2canvas-ignore="true"
              >
                {pdfBusy ? 'Building PDF…' : 'Download PDF'}
              </button>
            )}
          </div>

          {!insight && (
            <p className="subtle">No result file yet — run the desk and Sara will open the briefcase here.</p>
          )}

          {insight && (
            <div className="genai-memo briefcase-memo">
              <div className="genai-badge-row">
                <span className={`genai-stance stance-${insight.stance}`}>{pretty(insight.stance)}</span>
                {insight.confidence != null && <span className="subtle">Confidence {insight.confidence}</span>}
                <span className="subtle">
                  {result.from_cache
                    ? 'From vault'
                    : result.first_analysis
                      ? 'First analysis'
                      : `Used ${result.prior_insights_used} prior insight(s)`}
                </span>
              </div>
              <h4>Executive summary</h4>
              <p>{insight.executive_summary}</p>
              {insight.what_changed_vs_prior && (
                <>
                  <h4>What changed vs prior</h4>
                  <p>{insight.what_changed_vs_prior}</p>
                </>
              )}
              <div className="movers-grid" style={{ marginTop: 12 }}>
                <div>
                  <h4 className="up">Bull points</h4>
                  <ul className="reason-list compact">
                    {(insight.key_bull_points || []).length
                      ? insight.key_bull_points.map((x, i) => <li key={i}>{x}</li>)
                      : <li className="subtle">None in this memo</li>}
                  </ul>
                </div>
                <div>
                  <h4 className="down">Bear points</h4>
                  <ul className="reason-list compact">
                    {(insight.key_bear_points || []).length
                      ? insight.key_bear_points.map((x, i) => <li key={i}>{x}</li>)
                      : <li className="subtle">None in this memo</li>}
                  </ul>
                </div>
              </div>
              {insight.technical_read && <><h4>Technical read</h4><p>{insight.technical_read}</p></>}
              {insight.behavior_psych_read && (
                <>
                  <h4>Crowd behaviour read</h4>
                  <p>{insight.behavior_psych_read}</p>
                  {(result?.behavior_psych?.biases || []).length > 0 && (
                    <ul className="reason-list compact">
                      {result.behavior_psych.biases.slice(0, 4).map((x, i) => <li key={i}>{x}</li>)}
                    </ul>
                  )}
                </>
              )}
              {(insight.psychological_barriers_read || (result?.behavior_psych?.psychological_barriers || []).length > 0) && (
                <>
                  <h4>Psychological barriers</h4>
                  {insight.psychological_barriers_read && <p>{insight.psychological_barriers_read}</p>}
                  {(result?.behavior_psych?.psychological_barriers || []).length > 0 && (
                    <ul className="reason-list compact">
                      {result.behavior_psych.psychological_barriers.slice(0, 4).map((b, i) => (
                        <li key={i}>
                          <strong>{b.label}</strong> @ {b.level} ({b.distance_pct > 0 ? '+' : ''}{b.distance_pct}%)
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              )}
              {(insight.price_distortion_read || (result?.critical_signals?.price_distortion?.signals || []).length > 0) && (
                <>
                  <h4>Price distortion scan</h4>
                  {insight.price_distortion_read && <p>{insight.price_distortion_read}</p>}
                  {(result?.critical_signals?.price_distortion?.signals || []).length > 0 && (
                    <ul className="reason-list compact">
                      {result.critical_signals.price_distortion.signals.slice(0, 4).map((s, i) => (
                        <li key={i}>{s.plain_english}</li>
                      ))}
                    </ul>
                  )}
                </>
              )}
              {(insight.historical_distortion_read || (result?.critical_signals?.price_history?.episodes || []).length > 0) && (
                <>
                  <h4>5-year pump / dump history</h4>
                  {insight.historical_distortion_read && <p>{insight.historical_distortion_read}</p>}
                  {result?.critical_signals?.price_history?.recent_pump_dump_emphasis && (
                    <p className="critical-emphasis">{result.critical_signals.price_history.recent_pump_dump_emphasis}</p>
                  )}
                  {(result?.critical_signals?.price_history?.episodes || []).length > 0 && (
                    <ul className="reason-list compact">
                      {result.critical_signals.price_history.episodes.slice(-5).reverse().map((ep, i) => (
                        <li key={i}>{ep.plain_english || `${ep.type} ${ep.date || ep.dump_date}`}</li>
                      ))}
                    </ul>
                  )}
                </>
              )}
              {(insight.corporate_foundation_read || (result?.critical_signals?.corporate_foundation?.governance_headlines || []).length > 0) && (
                <>
                  <h4>Corporate foundation</h4>
                  {insight.corporate_foundation_read && <p>{insight.corporate_foundation_read}</p>}
                  {result?.critical_signals?.corporate_foundation?.ceo?.name && (
                    <p className="subtle">
                      {result.critical_signals.corporate_foundation.ceo.name}
                      {result.critical_signals.corporate_foundation.ceo.title ? ` · ${result.critical_signals.corporate_foundation.ceo.title}` : ''}
                    </p>
                  )}
                  {(result?.critical_signals?.corporate_foundation?.governance_headlines || []).length > 0 && (
                    <ul className="reason-list compact">
                      {result.critical_signals.corporate_foundation.governance_headlines.slice(0, 4).map((h, i) => (
                        <li key={i}>{h.title}</li>
                      ))}
                    </ul>
                  )}
                </>
              )}
              {(insight.government_policy_read || (result?.critical_signals?.government_policy?.headlines || []).length > 0) && (
                <>
                  <h4>Government policy</h4>
                  {insight.government_policy_read && <p>{insight.government_policy_read}</p>}
                  {(result?.critical_signals?.government_policy?.headlines || []).length > 0 && (
                    <ul className="reason-list compact news-headlines">
                      {result.critical_signals.government_policy.headlines.slice(0, 4).map((h, i) => (
                        <li key={i}>
                          <span className="news-tag tag-regulation-policy">{h.catalyst_label || 'Policy'}</span>
                          {' '}
                          {h.title}
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              )}
              {(insight.forum_intel_read || (result?.forum_intel?.threads || []).length > 0) && (
                <>
                  <h4>Forum &amp; community intel</h4>
                  {insight.forum_intel_read && <p>{insight.forum_intel_read}</p>}
                  <p className="subtle">{result?.forum_intel?.disclaimer || 'Public forum discussion — unverified, not insider facts.'}</p>
                  {(result?.forum_intel?.threads || []).length > 0 && (
                    <div className="news-catalyst-list">
                      <ul className="reason-list compact news-headlines">
                        {result.forum_intel.threads.slice(0, 8).map((t, i) => (
                          <li key={i}>
                            <span className={`news-tag tag-${(t.thread_tag || 'general_discussion').replace(/_/g, '-')}`}>
                              {t.thread_label || 'Discussion'}
                            </span>
                            {' '}
                            <span className="subtle">[{t.forum_label}] </span>
                            {t.url ? <a href={t.url} target="_blank" rel="noreferrer">{t.title}</a> : t.title}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </>
              )}
              {insight.fundamental_read && <><h4>Fundamental read</h4><p>{insight.fundamental_read}</p></>}
              {(insight.forecast_7d || result?.forecast_7d || result?.forecast_table) && (
                <ForecastTablePanel table={result?.forecast_table} insight={insight} />
              )}
              {(insight.forecast_accuracy_review || (result?.forecast_review?.reviews || []).length > 0) && (
                <>
                  <h4>Prior forecast accuracy</h4>
                  {insight.forecast_accuracy_review && <p>{insight.forecast_accuracy_review}</p>}
                  {(result?.forecast_review?.reviews || []).slice(0, 2).map((rev, i) => {
                    const sc = rev.score || {}
                    return (
                      <div key={i} className="forecast-review-row" style={{ marginBottom: 10 }}>
                        <p>
                          <span className={`genai-stance stance-${sc.label === 'accurate' ? 'bullish' : sc.label === 'missed' ? 'bearish' : 'neutral'}`}>
                            {pretty(sc.label || sc.maturity)}
                          </span>
                          {' '}
                          {sc.accuracy_pct != null && <span className="subtle">{sc.accuracy_pct}% accuracy</span>}
                          {rev.days_old != null && <span className="subtle"> · day {rev.days_old}</span>}
                        </p>
                        <p className="subtle">
                          Predicted {sc.predicted_direction} → {sc.target_price}; actual {sc.actual_return_pct != null ? `${sc.actual_return_pct > 0 ? '+' : ''}${sc.actual_return_pct}%` : '—'}
                        </p>
                        {sc.mismatch?.summary && <p>{sc.mismatch.summary}</p>}
                        {(sc.mismatch?.likely_events || []).length > 0 && (
                          <ul className="reason-list compact">
                            {sc.mismatch.likely_events.map((ev, j) => <li key={j}>{ev}</li>)}
                          </ul>
                        )}
                      </div>
                    )
                  })}
                </>
              )}
              {(insight.news_catalyst_read || (insight.macro_risks || []).length > 0 || (result?.news?.headlines || []).length > 0) && (
                <>
                  <h4>News &amp; macro catalysts</h4>
                  {insight.news_catalyst_read && <p>{insight.news_catalyst_read}</p>}
                  {(insight.macro_risks || []).length > 0 && (
                    <ul className="reason-list compact">
                      {insight.macro_risks.map((x, i) => <li key={i}>{x}</li>)}
                    </ul>
                  )}
                  {(result?.news?.headlines || []).length > 0 && (
                    <div className="news-catalyst-list">
                      <ul className="reason-list compact news-headlines">
                        {result.news.headlines.slice(0, 8).map((h, i) => (
                          <li key={i}>
                            <span className={`news-tag tag-${h.catalyst_tag || 'general'}`}>{h.catalyst_label || 'General'}</span>
                            {' '}
                            {h.url ? <a href={h.url} target="_blank" rel="noreferrer">{h.title}</a> : h.title}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </>
              )}
              {(insight.questions_to_monitor || []).length > 0 && (
                <>
                  <h4>Monitor</h4>
                  <ul className="reason-list compact">
                    {insight.questions_to_monitor.map((x, i) => <li key={i}>{x}</li>)}
                  </ul>
                </>
              )}
              <p className="subtle">{insight.not_advice_disclaimer || result.disclaimer}</p>
            </div>
          )}

          {(result?.history || []).length > 0 && (
            <div style={{ marginTop: 16 }}>
              <h4>Vault history</h4>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>When</th><th>Provider</th><th>Stance</th><th>Preview</th></tr>
                  </thead>
                  <tbody>
                    {result.history.map((h, i) => (
                      <tr key={i}>
                        <td>{h.created_at ? new Date(h.created_at).toLocaleString() : '—'}</td>
                        <td>{h.provider || '—'}</td>
                        <td>{h.stance || '—'}</td>
                        <td>{h.preview || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
        </div>
      )}
    </section>
  )
}


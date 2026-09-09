import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiGet, apiGetOptional, apiPatch, apiPost } from '../../lib/apiClient'
import { AppAlertList } from '../ui/AppAlert'
import { SymbolSearchField } from '../ui/SymbolSearchField'
import { TradePlanPanel } from './TradePlanPanel'
import { SessionReportsPanel } from './SessionReportsPanel'
import useConfirmDialog from '../../hooks/useConfirmDialog'
import { useSymbolSearch } from '../../hooks/useSymbolSearch'
import { normalizeAppSymbol, normalizeSymbolList, CURATED_SYMBOLS_MAX } from '../../lib/symbolValidate'

const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })

function formatEventTime(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return iso
  }
}

function eventLevelClass(level) {
  if (level === 'action') return 'up'
  if (level === 'skip' || level === 'warn') return 'down'
  if (level === 'complete') return ''
  return 'subtle'
}

function deskPnl(desk) {
  const realized = Number(desk?.realized_pnl_inr ?? 0)
  const unrealized = Number(desk?.unrealized_pnl_inr ?? 0)
  const net = Number(desk?.net_pnl_inr ?? realized + unrealized)
  return { realized, unrealized, net }
}

function SessionEventRow({ event, expanded, onToggle }) {
  const rationale = event.detail?.decision_rationale
  const thought = rationale?.thought_process
  return (
    <li className="session-event-row">
      <button type="button" className="session-event-head" onClick={onToggle}>
        <span className={`session-event-level ${eventLevelClass(event.level)}`}>{event.type}</span>
        {event._desk && <span className="session-event-desk">{event._desk}</span>}
        <span className="session-event-title">{event.title}</span>
        <span className="subtle">{formatEventTime(event.at)}</span>
      </button>
      {expanded && (
        <div className="session-event-detail">
          {thought && (
            <pre className="session-event-thought">{thought}</pre>
          )}
          <pre>{JSON.stringify(event.detail, null, 2)}</pre>
        </div>
      )}
    </li>
  )
}

export function AutopilotDesk() {
  const { confirm, dialog } = useConfirmDialog()
  const [config, setConfig] = useState(null)
  const [scoreboard, setScoreboard] = useState(null)
  const [alerts, setAlerts] = useState([])
  const [calibration, setCalibration] = useState(null)
  const [ledger, setLedger] = useState(null)
  const [intraday, setIntraday] = useState(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [statusMsg, setStatusMsg] = useState('')
  const [watchInput, setWatchInput] = useState('')
  const [morningScan, setMorningScan] = useState(null)
  const [quantDigest, setQuantDigest] = useState(null)
  const [timing, setTiming] = useState(null)
  const [ltpStream, setLtpStream] = useState(null)
  const [session, setSession] = useState(null)
  const [sessionTrades, setSessionTrades] = useState([])
  const [sessionEvents, setSessionEvents] = useState([])
  const [sessionCycles, setSessionCycles] = useState([])
  const [expandedEventId, setExpandedEventId] = useState(null)
  const [pickMode, setPickMode] = useState('curated_list')
  const [curatedSymbols, setCuratedSymbols] = useState([])
  const [maxSpend, setMaxSpend] = useState(200000)
  const [maxProfit, setMaxProfit] = useState(30000)
  const [maxLoss, setMaxLoss] = useState(15000)
  const [maxConcurrent, setMaxConcurrent] = useState(3)
  const [agentMaxSpend, setAgentMaxSpend] = useState(1000000)
  const [agentMaxProfit, setAgentMaxProfit] = useState(100000)
  const [agentMaxLoss, setAgentMaxLoss] = useState(15000)
  const [agentMaxConcurrent, setAgentMaxConcurrent] = useState(5)
  const [curatedMaxSpend, setCuratedMaxSpend] = useState(1000000)
  const [curatedMaxProfit, setCuratedMaxProfit] = useState(100000)
  const [curatedMaxLoss, setCuratedMaxLoss] = useState(15000)
  const [curatedMaxConcurrent, setCuratedMaxConcurrent] = useState(5)
  const [planPreview, setPlanPreview] = useState(null)
  const [planLoading, setPlanLoading] = useState(false)
  const [logRetention, setLogRetention] = useState('1d')
  const [eodReport, setEodReport] = useState(null)
  const [sessionReports, setSessionReports] = useState([])
  const [selectedReportId, setSelectedReportId] = useState('')
  const [lastProgressAt, setLastProgressAt] = useState(null)
  const [progressPolling, setProgressPolling] = useState(false)
  const [secondaryLoading, setSecondaryLoading] = useState(false)
  const [profitProfiles, setProfitProfiles] = useState(null)
  const symbolSearch = useSymbolSearch('')

  const fetchEodReport = useCallback(async (sessionId, { stale = false } = {}) => {
    if (!sessionId) {
      setEodReport(null)
      return
    }
    try {
      if (stale) {
        const report = await apiPost(`/api/trading/session/report/generate?session_id=${encodeURIComponent(sessionId)}`, {})
        setEodReport(report)
        return
      }
      const report = await apiGet(`/api/trading/session/report?session_id=${encodeURIComponent(sessionId)}`)
      setEodReport(report)
    } catch {
      try {
        const report = await apiPost(`/api/trading/session/report/generate?session_id=${encodeURIComponent(sessionId)}`, {})
        setEodReport(report)
      } catch {
        setEodReport(null)
      }
    }
  }, [])

  const savedCuratedSymbolsFromConfig = useCallback((cfg = config) => {
    const ap = cfg?.autopilot || {}
    return ap.dual_desk_preferences?.curated?.symbols?.length
      ? ap.dual_desk_preferences.curated.symbols
      : (ap.curated_symbols || [])
  }, [config])

  const mergeLiveDeskDetails = useCallback((liveDesks, details) => {
    const allEvents = []
    const allTrades = []
    const allCycles = []
    for (let i = 0; i < liveDesks.length; i++) {
      const desk = liveDesks[i]
      const detail = details[i] || {}
      const tag = desk.pick_mode === 'agent_auto' ? 'AI desk' : 'Curated'
      for (const ev of detail.events || []) {
        allEvents.push({ ...ev, _desk: tag })
      }
      for (const tr of detail.trades || []) {
        allTrades.push({ ...tr, _desk: tag })
      }
      for (const cy of detail.session?.cycles || []) {
        allCycles.push({ ...cy, _desk: tag, session_id: desk.id })
      }
    }
    allEvents.sort((a, b) => new Date(b.at || 0) - new Date(a.at || 0))
    allTrades.sort((a, b) => new Date(b.at || 0) - new Date(a.at || 0))
    allCycles.sort((a, b) => new Date(b.at || 0) - new Date(a.at || 0))
    setSessionEvents(allEvents.slice(0, 120))
    setSessionTrades(allTrades.slice(0, 120))
    setSessionCycles(allCycles.slice(0, 30))
    setEodReport(null)
    setLastProgressAt(new Date())
  }, [])

  const applyDeskPrefsFromConfig = useCallback((cfg, sess = null) => {
    const apCfg = cfg?.autopilot || {}
    const sessCfg = sess?.config || {}
    const dualPrefs = sessCfg.dual_desk_preferences || apCfg.dual_desk_preferences
    const isDual = Boolean(sess?.dual_mode || apCfg.dual_mode || apCfg.pick_mode === 'dual_desk')

    if (isDual && dualPrefs) {
      setPickMode('dual_desk')
      const agent = dualPrefs.agent || {}
      const curated = dualPrefs.curated || {}
      if (agent.max_spend_inr) setAgentMaxSpend(agent.max_spend_inr)
      if (agent.max_profit_inr) setAgentMaxProfit(agent.max_profit_inr)
      if (agent.max_loss_inr) setAgentMaxLoss(agent.max_loss_inr)
      if (agent.max_concurrent_picks) setAgentMaxConcurrent(agent.max_concurrent_picks)
      if (curated.max_spend_inr) setCuratedMaxSpend(curated.max_spend_inr)
      if (curated.max_profit_inr) setCuratedMaxProfit(curated.max_profit_inr)
      if (curated.max_loss_inr) setCuratedMaxLoss(curated.max_loss_inr)
      if (curated.max_concurrent_picks) setCuratedMaxConcurrent(curated.max_concurrent_picks)
      if (curated.symbols?.length) setCuratedSymbols(curated.symbols)
      else if (apCfg.curated_symbols?.length) setCuratedSymbols(apCfg.curated_symbols)
    } else if (isDual && sess?.sessions?.length >= 2) {
      setPickMode('dual_desk')
      const agentSess = sess.sessions.find(s => s.pick_mode === 'agent_auto')
      const curatedSess = sess.sessions.find(s => s.pick_mode === 'curated_list')
      if (agentSess?.caps) {
        setAgentMaxSpend(agentSess.caps.max_daily_notional_inr || agentMaxSpend)
        setAgentMaxProfit(agentSess.caps.max_profit_inr || agentMaxProfit)
        setAgentMaxLoss(agentSess.caps.max_intraday_loss_inr || agentMaxLoss)
        setAgentMaxConcurrent(agentSess.max_concurrent_picks || agentMaxConcurrent)
      }
      if (curatedSess) {
        setCuratedSymbols(curatedSess.curated_symbols || apCfg.curated_symbols || [])
        if (curatedSess.caps) {
          setCuratedMaxSpend(curatedSess.caps.max_daily_notional_inr || curatedMaxSpend)
          setCuratedMaxProfit(curatedSess.caps.max_profit_inr || curatedMaxProfit)
          setCuratedMaxLoss(curatedSess.caps.max_intraday_loss_inr || curatedMaxLoss)
          setCuratedMaxConcurrent(curatedSess.max_concurrent_picks || curatedMaxConcurrent)
        }
      }
    } else {
      setPickMode(apCfg.pick_mode || 'curated_list')
      setCuratedSymbols(apCfg.curated_symbols || [])
      setMaxConcurrent(apCfg.max_concurrent_picks || 3)
      const riskCfg = cfg.risk || {}
      if (riskCfg.max_daily_notional_inr) setMaxSpend(riskCfg.max_daily_notional_inr)
      if (riskCfg.max_profit_inr) setMaxProfit(riskCfg.max_profit_inr)
      if (riskCfg.max_intraday_loss_inr) setMaxLoss(riskCfg.max_intraday_loss_inr)
    }
  }, [agentMaxConcurrent, agentMaxLoss, agentMaxProfit, agentMaxSpend, curatedMaxConcurrent, curatedMaxLoss, curatedMaxProfit, curatedMaxSpend])

  const loadSessionDetails = useCallback(async (sess) => {
    if (!sess) return
    const displaySess = sess.display_session || sess.session
    const reportSid = sess.report_session_id || displaySess?.id
    const liveDesks = sess.active && (sess.sessions?.length ? sess.sessions : (sess.session ? [sess.session] : []))

    if (liveDesks?.length) {
      setProgressPolling(true)
      try {
        const details = await Promise.all(
          liveDesks.map(d => apiGetOptional(`/api/trading/session/detail?session_id=${encodeURIComponent(d.id)}`))
        )
        mergeLiveDeskDetails(liveDesks, liveDesks.map((_, i) => details[i] || {}))
      } finally {
        setProgressPolling(false)
      }
    } else if (sess.active && reportSid) {
      const detail = await apiGetOptional(`/api/trading/session/detail?session_id=${encodeURIComponent(reportSid)}`)
      if (detail) {
        setSessionTrades(detail.trades || [])
        setSessionEvents(detail.events || sess.recent_events || [])
        setSessionCycles(detail.session?.cycles || displaySess?.cycles || [])
        setEodReport(null)
      }
    } else if (!sess.active) {
      setSessionTrades([])
      setSessionEvents([])
      setSessionCycles([])
      setEodReport(null)
    } else if (sess.history?.[0]?.id) {
      const detail = await apiGetOptional(`/api/trading/session/detail?session_id=${sess.history[0].id}`)
      if (detail) {
        setSessionTrades(detail.trades || [])
        setSessionEvents(detail.events || [])
        setSessionCycles(detail.session?.cycles || [])
        await fetchEodReport(sess.history[0].id)
      }
    } else {
      setSessionTrades([])
      setSessionEvents(sess.recent_events || [])
      setSessionCycles([])
      setEodReport(null)
    }
    setLastProgressAt(new Date())
  }, [fetchEodReport, mergeLiveDeskDetails])

  const refresh = useCallback(async ({ clearError = false } = {}) => {
    if (clearError) setError('')
    try {
      const cfg = await apiGet('/api/trading/config')
      setConfig(cfg)
      setLedger(cfg.ledger)
      setWatchInput((cfg.watchlist || []).join(', '))
      applyDeskPrefsFromConfig(cfg)

      setSecondaryLoading(true)
      const [
        sb, al, cal, id, ms, qd, tm, ls, sess, reportsPayload, profitProf,
      ] = await Promise.all([
        apiGetOptional('/api/trading/scoreboard'),
        apiGetOptional('/api/trading/alerts'),
        apiGetOptional('/api/trading/calibration'),
        apiGetOptional('/api/trading/intraday/status'),
        apiGetOptional('/api/trading/morning-scan/status'),
        apiGetOptional('/api/quant/digest'),
        apiGetOptional('/api/trading/timing/status'),
        apiGetOptional('/api/broker/stream/status'),
        apiGetOptional('/api/trading/session/status'),
        apiGetOptional('/api/trading/session/reports?limit=50'),
        apiGetOptional('/api/trading/profit-profile'),
      ])
      setSecondaryLoading(false)

      if (sb) setScoreboard(sb)
      if (al) setAlerts(al.alerts || [])
      if (cal) setCalibration(cal)
      if (id) setIntraday(id)
      if (ms) setMorningScan(ms)
      if (qd && !qd.detail) setQuantDigest(qd)
      if (tm) setTiming(tm)
      if (ls) setLtpStream(ls)
      if (profitProf) setProfitProfiles(profitProf)
      if (reportsPayload) setSessionReports(reportsPayload.sessions || [])

      if (sess) {
        setSession(sess)
        applyDeskPrefsFromConfig(cfg, sess)
        void loadSessionDetails(sess)
      }
    } catch (e) {
      setSecondaryLoading(false)
      setProgressPolling(false)
      setError(e.message)
      const sess = await apiGetOptional('/api/trading/session/status')
      if (sess) setSession(sess)
    }
  }, [applyDeskPrefsFromConfig, loadSessionDetails])

  useEffect(() => { refresh({ clearError: true }) }, [refresh])

  useEffect(() => {
    if (!session?.active) return undefined
    const pollMs = 20000
    const id = setInterval(() => { refresh() }, pollMs)
    return () => clearInterval(id)
  }, [session?.active, refresh])

  async function patchConfig(partial) {
    setBusy('save')
    try {
      const res = await apiPatch('/api/trading/config', partial)
      setConfig(res.config)
      setLedger(res.ledger)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  async function armLive() {
    const ok = await confirm({
      title: 'Arm live trading',
      message: 'Real broker orders will be sent when mode is live and risk rules pass. Make sure broker credentials and caps are set.',
      confirmLabel: 'Arm live',
      cancelLabel: 'Cancel',
      variant: 'danger',
    })
    if (!ok) return
    setBusy('arm')
    try {
      await apiPost('/api/trading/config/arm-live?confirm=true', {})
      await refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  async function disarm() {
    setBusy('disarm')
    try {
      await apiPost('/api/trading/config/disarm', {})
      await refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  async function runAutopilot() {
    setBusy('run')
    try {
      await apiPost('/api/trading/autopilot/run', {})
      await refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  async function recalibrate() {
    setBusy('cal')
    try {
      const cal = await apiPost('/api/trading/calibration/recalibrate', {})
      setCalibration(cal)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  async function runPreLiveHygiene() {
    setBusy('hygiene')
    try {
      const result = await apiPost('/api/trading/pre-live-hygiene?run_quant_scan=false', {})
      setStatusMsg(
        `Hygiene: ${result.steps?.orphans?.count ?? 0} orphans squared, `
        + `${result.steps?.stale_sessions?.count ?? 0} stale sessions stopped`,
      )
      await refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  async function runDailyUniverse() {
    setBusy('daily-universe')
    try {
      const apCfg = config?.autopilot || {}
      await apiPost(
        `/api/trading/daily-universe/run?force=true&use_llm=${apCfg.quant_llm_synthesis_enabled === true}&conviction=${apCfg.daily_universe_conviction_enabled === true}`,
        {},
      )
      await refresh()
      setStatusMsg('Daily universe job completed (Agent0 + quant + morning scan).')
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  async function resetLearningRag() {
    const ok = await confirm({
      title: 'Reset all trading RAG?',
      message:
        'Clears Chroma insights, pick log, symbol blocks, timing lessons, and trade journal. '
        + 'Book RAG, price data, quant shortlist, and paper positions are kept.',
      confirmLabel: 'Reset learning',
      variant: 'danger',
    })
    if (!ok) return
    setBusy('learning-reset')
    try {
      const result = await apiPost('/api/trading/learning/reset?confirm=true', {})
      const chroma = result.chroma || {}
      setStatusMsg(
        `Learning reset: ${chroma.entries_before ?? 0} Chroma entries cleared, pick log wiped.`,
      )
      await refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  async function runQuantPipeline() {
    setBusy('quant')
    try {
      const apCfg = config?.autopilot || {}
      await apiPost('/api/quant/pipeline', {
        use_llm: apCfg.quant_llm_synthesis_enabled === true,
        max_shortlist: apCfg.quant_shortlist_max || 30,
      })
      await refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  async function runMorningScan() {
    setBusy('morning')
    try {
      await apiPost('/api/trading/morning-scan/run?force=true', {})
      await refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  async function syncLtpStream() {
    setBusy('ltp')
    try {
      await apiPost('/api/broker/stream/sync', {})
      await refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  async function learnTiming() {
    setBusy('timing')
    try {
      await apiPost('/api/trading/timing/learn', {})
      await refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  async function syncScoreboard() {
    setBusy('sync')
    try {
      await apiPost('/api/trading/scoreboard/sync', {})
      const sb = await apiGet('/api/trading/scoreboard')
      setScoreboard(sb)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  const mode = config?.execution_mode || 'paper'
  const armed = config?.live_armed
  const ap = config?.autopilot || {}
  const risk = config?.risk || {}
  const snap = config?.risk_snapshot || {}
  const halted = ledger?.halted || snap.halted
  const dualPrefs = ap.dual_desk_preferences
  const activeProfitProfile = profitProfiles?.active || ap.profit_profile || 'conservative'
  const profitProfileOptions = profitProfiles?.profiles || []
  const homeRunRec = profitProfiles?.home_run_recommendation
  const isDualConfig = pickMode === 'dual_desk' || ap.pick_mode === 'dual_desk' || ap.dual_mode
  const deskLossCap = isDualConfig && dualPrefs
    ? (Number(dualPrefs.agent?.max_loss_inr) || 0) + (Number(dualPrefs.curated?.max_loss_inr) || 0)
    : Number(agentMaxLoss || maxLoss || risk.max_intraday_loss_inr || 0)
  const globalLossCap = Number(risk.max_intraday_loss_inr || 0)
  const buyCapDisplay = isDualConfig && dualPrefs
    ? (Number(dualPrefs.agent?.max_spend_inr) || 0) + (Number(dualPrefs.curated?.max_spend_inr) || 0)
    : snap.buy_notional_cap_inr

  function patchRisk(field, value) {
    patchConfig({ risk: { ...risk, [field]: value } })
  }

  async function applyProfitProfile(profileId) {
    if (sessionActive) {
      setError('Stop the session before switching profit profile.')
      return
    }
    setBusy('profit-profile')
    setError('')
    try {
      const res = await apiPost('/api/trading/profit-profile', { profile: profileId })
      setConfig(res.config)
      setProfitProfiles(prev => ({ ...(prev || {}), active: res.profile, profiles: prev?.profiles }))
      setStatusMsg(res.message || `Profile: ${res.label}`)
      const dual = res.config?.autopilot?.dual_desk_preferences || {}
      if (dual.agent?.max_profit_inr) setAgentMaxProfit(dual.agent.max_profit_inr)
      if (dual.curated?.max_profit_inr) setCuratedMaxProfit(dual.curated.max_profit_inr)
      const riskCfg = res.config?.risk || {}
      if (riskCfg.max_daily_notional_inr) setMaxSpend(riskCfg.max_daily_notional_inr)
      if (riskCfg.max_profit_inr) setMaxProfit(riskCfg.max_profit_inr)
      await refresh({ clearError: true })
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  async function clearHalt() {
    setBusy('halt')
    try {
      await apiPost('/api/trading/risk/clear-halt', {})
      await refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  async function addCuratedSymbol(pickedSymbol) {
    const raw = pickedSymbol || await symbolSearch.resolveSymbol()
    if (!raw) {
      setError('Pick a symbol from search results (.NSE or .BSE required).')
      return
    }
    let sym
    try {
      sym = normalizeAppSymbol(raw)
    } catch (e) {
      setError(e.message)
      return
    }
    setError('')
    setCuratedSymbols(prev => {
      if (prev.includes(sym)) return prev
      if (prev.length >= CURATED_SYMBOLS_MAX) {
        setError(`Maximum ${CURATED_SYMBOLS_MAX} stocks.`)
        return prev
      }
      return [...prev, sym]
    })
    symbolSearch.setQuery('')
    symbolSearch.clearSuggestions()
  }

  function removeCuratedSymbol(sym) {
    setCuratedSymbols(prev => prev.filter(s => s !== sym))
  }

  async function saveCuratedList() {
    if (curatedSymbols.length < 1) {
      setError('Add at least 1 stock to save.')
      return
    }
    let syms
    try {
      syms = normalizeSymbolList(curatedSymbols, { minCount: 1, maxCount: CURATED_SYMBOLS_MAX })
    } catch (e) {
      setError(e.message)
      return
    }
    setBusy('save-list')
    try {
      const apPatch = {
        curated_symbols: syms,
      }
      const existingPrefs = config?.autopilot?.dual_desk_preferences
      if (pickMode === 'dual_desk' || existingPrefs) {
        apPatch.dual_desk_preferences = {
          ...(existingPrefs || {}),
          curated: {
            ...(existingPrefs?.curated || {}),
            symbols: syms,
          },
        }
      }
      await patchConfig({ watchlist: syms, autopilot: apPatch })
      setCuratedSymbols(syms)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  async function copyCuratedList() {
    if (!curatedSymbols.length) {
      setError('No stocks to copy.')
      return
    }
    const text = curatedSymbols.join('\n')
    try {
      await navigator.clipboard.writeText(text)
      setError('')
    } catch (e) {
      setError(e.message || 'Could not copy to clipboard.')
    }
  }

  async function pasteCuratedList() {
    setBusy('paste-list')
    try {
      const text = await navigator.clipboard.readText()
      const raw = text.split(/[\n,;\s]+/).map(s => s.trim()).filter(Boolean)
      const merged = [...curatedSymbols]
      for (const part of raw) {
        if (merged.length >= CURATED_SYMBOLS_MAX) break
        try {
          const sym = normalizeAppSymbol(part)
          if (!merged.includes(sym)) merged.push(sym)
        } catch {
          /* skip invalid token */
        }
      }
      if (merged.length === curatedSymbols.length) {
        setError('Nothing valid to paste from clipboard.')
        return
      }
      setCuratedSymbols(merged)
      setError('')
    } catch (e) {
      setError(e.message || 'Could not read clipboard.')
    } finally {
      setBusy('')
    }
  }

  async function startSession() {
    if (pickMode === 'dual_desk') {
      return startDualSession()
    }
    if (pickMode === 'curated_list' && curatedSymbols.length < 1) {
      setError('Add at least 1 stock for curated-list mode.')
      return
    }
    let sessionSymbols = curatedSymbols
    if (pickMode === 'curated_list') {
      try {
        sessionSymbols = normalizeSymbolList(curatedSymbols, { minCount: 1, maxCount: CURATED_SYMBOLS_MAX })
      } catch (e) {
        setError(e.message)
        return
      }
    }
    const ok = await confirm({
      title: 'Start all-day autopilot session',
      message: pickMode === 'curated_list'
        ? `Trade from ${sessionSymbols.length} selected stocks (max ${maxConcurrent} concurrent). Caps: spend ₹${maxSpend.toLocaleString('en-IN')}, profit ₹${maxProfit.toLocaleString('en-IN')}, loss ₹${maxLoss.toLocaleString('en-IN')}.`
        : `Agent picks from Nifty 500 / morning scan. Same caps apply.`,
      confirmLabel: 'Start session',
      cancelLabel: 'Cancel',
      variant: 'danger',
    })
    if (!ok) return
    setBusy('session')
    try {
      await apiPost('/api/trading/session/start', {
        pick_mode: pickMode,
        symbols: pickMode === 'curated_list' ? sessionSymbols : null,
        max_spend_inr: maxSpend,
        max_profit_inr: maxProfit,
        max_loss_inr: maxLoss,
        max_concurrent_picks: maxConcurrent,
      })
      await patchConfig({ watchlist: sessionSymbols, autopilot: { curated_symbols: sessionSymbols } })
      await refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  async function startDualSession() {
    const symbolSource = curatedSymbols.length
      ? curatedSymbols
      : savedCuratedSymbolsFromConfig()
    if (symbolSource.length < 1) {
      setStatusMsg('')
      setError('Add at least 1 stock for the curated desk (search above, or click Save list).')
      return
    }
    let sessionSymbols
    try {
      sessionSymbols = normalizeSymbolList(symbolSource, { minCount: 1, maxCount: CURATED_SYMBOLS_MAX })
    } catch (e) {
      setStatusMsg('')
      setError(e.message)
      return
    }
    if (!curatedSymbols.length && sessionSymbols.length) {
      setCuratedSymbols(sessionSymbols)
    }
    const ok = await confirm({
      title: 'Start dual desk session',
      message: `Run AI auto-pick (₹${agentMaxSpend.toLocaleString('en-IN')} budget) and curated list (${sessionSymbols.length} stocks, ₹${curatedMaxSpend.toLocaleString('en-IN')} budget) in parallel.${todayPnl?.orphanPnl?.count ? ' Legacy open positions will be squared automatically before start.' : ''}`,
      confirmLabel: 'Start both desks',
      cancelLabel: 'Cancel',
      variant: 'danger',
    })
    if (!ok) return
    setBusy('session')
    setStatusMsg('')
    try {
      await apiPost('/api/trading/session/start-dual', {
        agent_max_spend_inr: agentMaxSpend,
        agent_max_profit_inr: agentMaxProfit,
        agent_max_loss_inr: agentMaxLoss,
        agent_max_concurrent_picks: agentMaxConcurrent,
        curated_symbols: sessionSymbols,
        curated_max_spend_inr: curatedMaxSpend,
        curated_max_profit_inr: curatedMaxProfit,
        curated_max_loss_inr: curatedMaxLoss,
        curated_max_concurrent_picks: curatedMaxConcurrent,
      })
      const sess = await apiGet('/api/trading/session/status')
      setSession(sess)
      setPickMode('dual_desk')
      setError('')
      setStatusMsg(`Dual desk live — AI desk + ${sessionSymbols.length} curated stocks.`)
      const liveDesks = sess?.sessions?.length
        ? sess.sessions
        : (sess?.session ? [sess.session] : [])
      if (liveDesks.length) {
        setProgressPolling(true)
        try {
          const details = await Promise.all(
            liveDesks.map(d => apiGet(`/api/trading/session/detail?session_id=${encodeURIComponent(d.id)}`))
          )
          mergeLiveDeskDetails(liveDesks, details)
        } finally {
          setProgressPolling(false)
        }
      }
      refresh().catch(e => setError(e.message))
    } catch (e) {
      setStatusMsg('')
      setError(e.message)
      if (/stop existing session/i.test(e.message || '')) {
        try {
          const sess = await apiGet('/api/trading/session/status')
          setSession(sess)
        } catch (_) {
          /* ignore */
        }
      }
    } finally {
      setBusy('')
    }
  }

  async function openSessionReport(sessionId) {
    if (!sessionId) return
    setSelectedReportId(sessionId)
    setBusy('report')
    try {
      await fetchEodReport(sessionId, { stale: true })
      const detail = await apiGet(`/api/trading/session/detail?session_id=${encodeURIComponent(sessionId)}`)
      setSessionTrades(detail.trades || [])
      setSessionEvents(detail.events || [])
      setSessionCycles(detail.session?.cycles || [])
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  async function downloadSessionReportPdf(sessionId) {
    if (!sessionId) return
    setBusy('pdf')
    try {
      const res = await fetch(`/api/trading/session/report/pdf?session_id=${encodeURIComponent(sessionId)}`)
      if (!res.ok) {
        const fail = await res.json().catch(() => ({}))
        throw new Error(fail.detail || `HTTP ${res.status}`)
      }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${sessionId}_report.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  async function stopSession(sessionId = null) {
    setBusy('session')
    try {
      await apiPost('/api/trading/session/stop', sessionId ? { session_id: sessionId } : {})
      setSessionTrades([])
      setSessionEvents([])
      setSessionCycles([])
      setEodReport(null)
      setStatusMsg('')
      setExpandedEventId(null)
      await refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  async function squareOrphanPositions() {
    const count = todayPnl?.orphanPnl?.count || 0
    if (count < 1) return
    const ok = await confirm({
      title: 'Square legacy positions',
      message: `Close ${count} open position(s) from prior sessions at market price? Active desk positions are not touched.`,
      confirmLabel: 'Square all',
      cancelLabel: 'Cancel',
      variant: 'danger',
    })
    if (!ok) return
    setBusy('square-orphans')
    try {
      const result = await apiPost('/api/trading/session/square-orphans', {})
      setError('')
      setStatusMsg(`Squared ${result.count ?? 0} legacy position(s).`)
      await refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  async function clearSessionLog() {
    const labels = { '1h': '1 hour', '12h': '12 hours', '1d': '1 day', '7d': '7 days' }
    const ok = await confirm({
      title: 'Clear autopilot log',
      message: `Delete all log entries older than ${labels[logRetention] || logRetention}? Recent entries within that window are kept.`,
      confirmLabel: 'Clear older logs',
      cancelLabel: 'Cancel',
      variant: 'danger',
    })
    if (!ok) return
    setBusy('clear-log')
    try {
      await apiPost('/api/trading/session/events/clear', { retention: logRetention })
      await refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  const activeSessions = session?.sessions?.length
    ? session.sessions.filter(s => s?.status === 'active')
    : (session?.session?.status === 'active' ? [session.session] : [])
  const sessionActive = Boolean(session?.active) || activeSessions.length > 0
  const stopExistingSessionError = /stop existing session/i.test(error || '')
  const activeSessionIds = useMemo(
    () => new Set(activeSessions.map(d => d.id).filter(Boolean)),
    [activeSessions],
  )

  const visibleSessionTrades = useMemo(() => {
    const seen = new Set()
    return sessionTrades
      .filter(r => r.side !== 'buy_skipped')
      .filter(r => !activeSessionIds.size || activeSessionIds.has(r.session_id))
      .filter(r => {
        const key = r.id || `${r.session_id}-${r.at}-${r.side}-${r.symbol}-${r.quantity}`
        if (seen.has(key)) return false
        seen.add(key)
        return true
      })
  }, [sessionTrades, activeSessionIds])
  const dualMode = Boolean(session?.dual_mode || activeSessions.length > 1)
  const activeSession = session?.display_session || session?.session
  const sessionPnl = activeSession?.realized_pnl_inr ?? ledger?.daily?.realized_pnl_inr ?? 0
  const sessionCycleCount = activeSession?.cycle_count ?? activeSession?.cycles?.length ?? 0
  const latestCycle = sessionCycles[0]
  const latestAudit = latestCycle?.universe_audit || []
  const nseInfo = session?.nse
  const premarketPlan = session?.premarket_plan || activeSession?.premarket_plan
  const macSleepGuard = session?.mac_sleep_guard

  const todayPnl = useMemo(() => {
    const globalRealized = Number(ledger?.daily?.realized_pnl_inr ?? snap.realized_pnl_inr ?? 0)
    const globalUnrealized = Number(snap.unrealized_pnl_inr ?? 0)
    const globalNet = globalRealized + globalUnrealized
    const dateLabel = ledger?.daily?.date
      ? new Date(`${ledger.daily.date}T12:00:00`).toLocaleDateString('en-IN', {
        weekday: 'short',
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      })
      : new Date().toLocaleDateString('en-IN', {
        weekday: 'short',
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      })
    const allOpenPositions = (ledger?.positions || []).filter(p => Number(p.quantity) > 0)
    const deskRows = activeSessions.map(desk => {
      const pnl = deskPnl(desk)
      return {
        id: desk.id,
        label: desk.pick_mode === 'agent_auto' ? 'AI auto-pick' : 'Curated list',
        ...pnl,
      }
    })
    const deskScoped = session?.desk_pnl
      ? {
        realized: Number(session.desk_pnl.realized_pnl_inr ?? 0),
        unrealized: Number(session.desk_pnl.unrealized_pnl_inr ?? 0),
        net: Number(session.desk_pnl.net_pnl_inr ?? 0),
      }
      : session?.dual_desk_pnl
        ? {
          realized: Number(session.dual_desk_pnl.realized_pnl_inr ?? 0),
          unrealized: Number(session.dual_desk_pnl.unrealized_pnl_inr ?? 0),
          net: Number(session.dual_desk_pnl.net_pnl_inr ?? 0),
        }
        : deskRows.length === 1
          ? { realized: deskRows[0].realized, unrealized: deskRows[0].unrealized, net: deskRows[0].net }
          : null
    const orphanPnl = session?.orphan_pnl
      ? {
        count: Number(session.orphan_pnl.position_count ?? 0),
        unrealized: Number(session.orphan_pnl.unrealized_pnl_inr ?? 0),
        net: Number(session.orphan_pnl.net_pnl_inr ?? 0),
        symbols: session.orphan_pnl.symbols || [],
      }
      : null
    const useDeskScope = Boolean(sessionActive && deskScoped)
    const realized = useDeskScope ? deskScoped.realized : globalRealized
    const unrealized = useDeskScope ? deskScoped.unrealized : globalUnrealized
    const net = useDeskScope ? deskScoped.net : globalNet
    const openPositions = useDeskScope
      ? allOpenPositions.filter(p => activeSessionIds.has(p.session_id))
      : allOpenPositions
    const dualSummary = deskScoped && deskRows.length > 1 ? deskScoped : null
    return {
      realized,
      unrealized,
      net,
      globalRealized,
      globalUnrealized,
      globalNet,
      useDeskScope,
      orphanPnl,
      dateLabel,
      orders: ledger?.daily?.orders ?? snap.orders_today ?? 0,
      buyNotional: ledger?.daily?.buy_notional_inr ?? snap.buy_notional_used_inr ?? 0,
      openCount: openPositions.length,
      openPositions,
      allOpenCount: allOpenPositions.length,
      deskRows,
      dualSummary,
    }
  }, [ledger, snap, activeSessions, session?.desk_pnl, session?.dual_desk_pnl, session?.orphan_pnl, sessionActive, activeSessionIds])

  useEffect(() => {
    if (premarketPlan?.symbol_entries?.length || premarketPlan?.planned_picks?.length) {
      setPlanPreview(null)
      return undefined
    }
    if (pickMode !== 'curated_list' || curatedSymbols.length === 0) {
      setPlanPreview(null)
      return undefined
    }
    let cancelled = false
    const timer = setTimeout(async () => {
      setPlanLoading(true)
      try {
        const q = encodeURIComponent(curatedSymbols.join(','))
        const data = await apiGet(`/api/trading/plan/preview?symbols=${q}`)
        if (!cancelled) setPlanPreview(data)
      } catch {
        if (!cancelled) setPlanPreview(null)
      } finally {
        if (!cancelled) setPlanLoading(false)
      }
    }, 500)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [pickMode, curatedSymbols, premarketPlan])

  const intradayRules = premarketPlan?.intraday_rules || session?.intraday_rules || planPreview?.intraday_rules || {
    style: 'intraday_mis',
    product: 'MIS',
    horizon: 'same day',
    target_pct: config?.autopilot?.target_pct ?? config?.risk?.default_target_pct ?? 1.5,
    stop_pct: config?.autopilot?.stop_pct ?? config?.risk?.default_stop_pct ?? 0.75,
    min_composite: config?.risk?.agent_min_composite ?? config?.autopilot?.entry_min_composite ?? 55,
    square_off_ist: (() => {
      const m = config?.autopilot?.square_off_minute_ist ?? 920
      return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
    })(),
    entry_strategy: 'Market MIS buy at LTP when timing gate allows',
    exit_strategy: 'Sell on target, stop, or mandatory EOD square-off',
    reentry: 'Allowed after profit booked until session caps',
  }
  const swingRules = session?.swing_rules || planPreview?.swing_rules
  const planRows = useMemo(() => {
    if (premarketPlan?.planned_picks?.length) return premarketPlan.planned_picks
    if (premarketPlan?.symbol_entries?.length) return premarketPlan.symbol_entries
    if (planPreview?.planned_picks?.length) return planPreview.planned_picks
    return planPreview?.symbols || []
  }, [premarketPlan, planPreview])
  const planSourceLabel = premarketPlan
    ? `Pre-market plan · ${premarketPlan.trade_date_ist || 'today'}`
    : planPreview
      ? 'Live preview (dry run)'
      : ''

  if (!config) {
    return (
      <div className="autopilot-desk">
        <section className="panel">
          <p className="subtle">Loading trading config…</p>
          {error && (
            <p className="down">
              {error}
              {/backend|port 8000|running/i.test(error) && (
                <span className="subtle"> — run <code>./scripts/dev.sh</code> from the project root.</span>
              )}
            </p>
          )}
        </section>
        {dialog}
      </div>
    )
  }

  return (
    <div className="autopilot-desk">
      {todayPnl.orphanPnl?.count > 0 && (
        <section className="panel orphan-alert-banner" role="alert">
          <div className="orphan-alert-body">
            <div>
              <p className="eyebrow">LEGACY POSITIONS</p>
              <strong>
                {todayPnl.orphanPnl.count} open leg{todayPnl.orphanPnl.count === 1 ? '' : 's'} from a prior session
              </strong>
              <p className="subtle orphan-alert-detail">
                Unrealized{' '}
                <span className={todayPnl.orphanPnl.unrealized >= 0 ? 'up' : 'down'}>
                  {money.format(todayPnl.orphanPnl.unrealized)}
                </span>
                {todayPnl.orphanPnl.symbols?.length > 0 && (
                  <> · {todayPnl.orphanPnl.symbols.join(', ')}</>
                )}
                {' · '}
                Square all before restarting dual desk — orphan RPTECH-style leaks destroyed Aug 14 book P/L.
              </p>
            </div>
            <button
              type="button"
              className="primary orphan-alert-action"
              disabled={!!busy}
              onClick={squareOrphanPositions}
            >
              Square all
            </button>
          </div>
        </section>
      )}
      <section className="panel today-pnl-panel">
        <div className="panel-head">
          <div>
            <p className="eyebrow">TODAY&apos;S P&amp;L</p>
            <h3>{todayPnl.dateLabel}</h3>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            {sessionActive && <span className="live-pill is-live">LIVE</span>}
            {(lastProgressAt || progressPolling || secondaryLoading) && (
              <span className="subtle">
                {progressPolling || secondaryLoading ? 'Updating…' : `Updated ${lastProgressAt.toLocaleTimeString('en-IN')}`}
              </span>
            )}
            <button type="button" className="ghost" disabled={!!busy || progressPolling} onClick={() => refresh({ clearError: true })}>
              Refresh
            </button>
          </div>
        </div>
        <div className="today-pnl-hero">
          <article className="today-pnl-stat today-pnl-stat--net">
            <p>Net P&amp;L</p>
            <strong className={todayPnl.net >= 0 ? 'up' : 'down'}>{money.format(todayPnl.net)}</strong>
            <span className="subtle">
              {todayPnl.useDeskScope ? 'active desk(s) · realized + unrealized' : 'realized + unrealized'}
            </span>
          </article>
          <article className="today-pnl-stat">
            <p>Realized</p>
            <strong className={todayPnl.realized >= 0 ? 'up' : 'down'}>{money.format(todayPnl.realized)}</strong>
            <span className="subtle">closed trades</span>
          </article>
          <article className="today-pnl-stat">
            <p>Unrealized</p>
            <strong className={todayPnl.unrealized >= 0 ? 'up' : 'down'}>{money.format(todayPnl.unrealized)}</strong>
            <span className="subtle">open positions</span>
          </article>
          <article className="today-pnl-stat">
            <p>Orders</p>
            <strong>{todayPnl.orders}</strong>
            <span className="subtle">{todayPnl.openCount} open</span>
          </article>
          <article className="today-pnl-stat">
            <p>Buy notional</p>
            <strong>{money.format(todayPnl.buyNotional)}</strong>
            <span className="subtle">deployed today</span>
          </article>
        </div>
        {todayPnl.deskRows.length > 0 && (
          <div className="today-pnl-desks">
            {todayPnl.dualSummary && (
              <p className="subtle today-pnl-desk-row">
                <b>Dual desk total</b>
                {' · '}
                Net{' '}
                <strong className={todayPnl.dualSummary.net >= 0 ? 'up' : 'down'}>
                  {money.format(todayPnl.dualSummary.net)}
                </strong>
                {' · '}
                Realized {money.format(todayPnl.dualSummary.realized)}
                {' · '}
                Unrealized{' '}
                <strong className={todayPnl.dualSummary.unrealized >= 0 ? 'up' : 'down'}>
                  {money.format(todayPnl.dualSummary.unrealized)}
                </strong>
              </p>
            )}
            {todayPnl.deskRows.map(row => (
              <p key={row.id} className="subtle today-pnl-desk-row">
                <b>{row.label}</b>
                {' · '}
                Net{' '}
                <strong className={row.net >= 0 ? 'up' : 'down'}>{money.format(row.net)}</strong>
                {' · '}
                Realized {money.format(row.realized)}
                {' · '}
                Unrealized{' '}
                <strong className={row.unrealized >= 0 ? 'up' : 'down'}>{money.format(row.unrealized)}</strong>
              </p>
            ))}
          </div>
        )}
        {todayPnl.orphanPnl?.count > 0 && (
          <p className="subtle today-pnl-desk-row">
            <b>Legacy positions</b> (old session, not in current desk)
            {' · '}
            {todayPnl.orphanPnl.count} open
            {' · '}
            Unrealized{' '}
            <strong className={todayPnl.orphanPnl.unrealized >= 0 ? 'up' : 'down'}>
              {money.format(todayPnl.orphanPnl.unrealized)}
            </strong>
            {todayPnl.orphanPnl.symbols?.length > 0 && (
              <> · {todayPnl.orphanPnl.symbols.join(', ')}</>
            )}
            {' · '}
            Ledger total {money.format(todayPnl.globalNet)} incl. these
          </p>
        )}
        {todayPnl.openPositions.length > 0 && (
          <div className="today-pnl-open">
            <p className="eyebrow" style={{ marginBottom: 6 }}>Open positions</p>
            <ul className="reason-list compact">
              {todayPnl.openPositions.slice(0, 8).map(pos => (
                <li key={pos.symbol}>
                  {pos.symbol}
                  {' · '}
                  {pos.quantity} @ {money.format(pos.avg_price || pos.entry_price || 0)}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      {sessionActive && (
        <section className="panel session-progress-panel">
          <div className="panel-head">
            <div>
              <p className="eyebrow">LIVE SESSION PROGRESS</p>
              <h3>{dualMode ? 'Dual desk running' : 'Session running'}</h3>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <span className="live-pill is-live">LIVE</span>
              {progressPolling && <span className="subtle">Updating…</span>}
              {lastProgressAt && (
                <span className="subtle">Updated {lastProgressAt.toLocaleTimeString('en-IN')}</span>
              )}
              <button type="button" className="ghost" disabled={!!busy || progressPolling} onClick={() => refresh({ clearError: true })}>
                Refresh now
              </button>
            </div>
          </div>
          {nseInfo && (
            <p className="session-progress-phase">
              <b>{nseInfo.ist_time} IST</b> · {nseInfo.label}
              {nseInfo.minutes_to_open > 0 && <> · Opens in {nseInfo.minutes_to_open} min</>}
            </p>
          )}
          {dualMode && todayPnl.dualSummary && (
            <div className="session-desk-summary">
              <p className="session-desk-card-stat">
                Combined net P&amp;L{' '}
                <strong className={todayPnl.dualSummary.net >= 0 ? 'up' : 'down'}>
                  {money.format(todayPnl.dualSummary.net)}
                </strong>
              </p>
              <p className="subtle">
                Realized {money.format(todayPnl.dualSummary.realized)}
                {' · '}
                Unrealized{' '}
                <strong className={todayPnl.dualSummary.unrealized >= 0 ? 'up' : 'down'}>
                  {money.format(todayPnl.dualSummary.unrealized)}
                </strong>
              </p>
            </div>
          )}
          <div className="session-progress-desks">
            {(activeSessions.length ? activeSessions : (activeSession ? [activeSession] : [])).map(desk => {
              const deskEvents = sessionEvents.filter(e => e.session_id === desk.id || e._desk?.startsWith(desk.pick_mode === 'agent_auto' ? 'AI' : 'Curated'))
              const lastEv = deskEvents[0]
              const deskTrades = sessionTrades.filter(t => t.session_id === desk.id)
              const buys = deskTrades.filter(t => t.side === 'buy').length
              const sells = deskTrades.filter(t => t.side === 'sell').length
              const pnl = deskPnl(desk)
              return (
                <article key={desk.id} className="session-desk-card">
                  <p className="session-desk-card-title">
                    {desk.pick_mode === 'agent_auto' ? 'AI auto-pick' : 'Curated list'}
                  </p>
                  <p className="session-desk-card-stat">
                    Net P&amp;L{' '}
                    <strong className={pnl.net >= 0 ? 'up' : 'down'}>
                      {money.format(pnl.net)}
                    </strong>
                  </p>
                  <p className="subtle">
                    Realized {money.format(pnl.realized)}
                    {' · '}
                    Unrealized{' '}
                    <strong className={pnl.unrealized >= 0 ? 'up' : 'down'}>
                      {money.format(pnl.unrealized)}
                    </strong>
                  </p>
                  <p className="subtle">
                    {desk.cycle_count ?? desk.cycles?.length ?? 0} cycles · {buys} buys · {sells} sells
                  </p>
                  {desk.caps && (
                    <p className="subtle">Budget {money.format(desk.caps.max_daily_notional_inr)}</p>
                  )}
                  {desk.pick_mode === 'curated_list' && desk.curated_symbols?.length > 0 && (
                    <p className="subtle session-desk-symbols">{desk.curated_symbols.length} stocks</p>
                  )}
                  {lastEv && (
                    <p className="session-desk-last-event">
                      Last: <span className={`session-event-level ${eventLevelClass(lastEv.level)}`}>{lastEv.type}</span>{' '}
                      {lastEv.title}
                    </p>
                  )}
                </article>
              )
            })}
          </div>
          {sessionEvents.length > 0 && (
            <>
              <p className="eyebrow" style={{ marginTop: 14 }}>Recent activity</p>
              <ul className="session-progress-feed">
                {sessionEvents.slice(0, 12).map(ev => (
                  <li key={ev.id} className={`session-progress-feed-item level-${ev.level || 'info'}`}>
                    <span className="subtle">{formatEventTime(ev.at)}</span>
                    {ev._desk && <span className="session-event-desk">{ev._desk}</span>}
                    <span className={`session-event-level ${eventLevelClass(ev.level)}`}>{ev.type}</span>
                    <span>{ev.title}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
          {sessionEvents.length === 0 && (
            <p className="subtle" style={{ marginTop: 10 }}>
              Waiting for first scheduler cycle… Autopilot polls every ~2 min (faster during market open).
            </p>
          )}
        </section>
      )}

      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="eyebrow">EXECUTION DESK</p>
            <h3>Paper / Live · Autopilot · Risk caps</h3>
          </div>
          <span className={`live-pill ${mode === 'live' && armed ? 'is-live' : ''}`}>
            {mode === 'live' && armed ? 'LIVE ARMED' : mode.toUpperCase()}
          </span>
        </div>
        <p className="subtle">
          Educational simulation. Paper fills use broker/Yahoo rates. Live requires Groww/Kite/FYERS + arm confirm.
        </p>
        {error && <p className="down">{error}</p>}
        {halted && (
          <div className="app-alert app-alert--warn" style={{ marginBottom: 12 }}>
            <div className="app-alert-head">
              <span className="app-alert-badge">Halted</span>
            </div>
            <p className="app-alert-message">{ledger?.halt_reason || snap.halt_reason || 'Auto trading halted for today.'}</p>
            <button type="button" className="ghost" style={{ marginTop: 8 }} disabled={!!busy} onClick={clearHalt}>Clear halt (manual)</button>
          </div>
        )}

        <div className="autopilot-controls">
          <label className="refresh-toggle">
            <input
              type="radio"
              name="exec-mode"
              checked={mode === 'paper'}
              onChange={() => patchConfig({ execution_mode: 'paper', live_armed: false })}
            />
            Paper
          </label>
          <label className="refresh-toggle">
            <input
              type="radio"
              name="exec-mode"
              checked={mode === 'live'}
              onChange={() => patchConfig({ execution_mode: 'live' })}
            />
            Live (needs arm)
          </label>
          <button type="button" className="ghost" disabled={busy} onClick={armLive}>Arm live</button>
          <button type="button" className="ghost" disabled={busy} onClick={disarm}>Disarm</button>
        </div>

        <div className="metrics" style={{ marginTop: 12 }}>
          <article className="metric">
            <p>Orders today</p>
            <strong>{ledger?.daily?.orders ?? '—'}</strong>
          </article>
          <article className="metric">
            <p>Day P&amp;L (realized)</p>
            <strong className={(ledger?.daily?.realized_pnl_inr || 0) >= 0 ? 'up' : 'down'}>
              {money.format(ledger?.daily?.realized_pnl_inr || 0)}
            </strong>
          </article>
          <article className="metric">
            <p>Unrealized</p>
            <strong className={(snap.unrealized_pnl_inr || 0) >= 0 ? 'up' : 'down'}>
              {money.format(snap.unrealized_pnl_inr || 0)}
            </strong>
          </article>
          <article className="metric">
            <p>Buy bucket used</p>
            <strong>
              {money.format(snap.buy_notional_used_inr || 0)}
              {buyCapDisplay ? ` / ${money.format(buyCapDisplay)}` : ''}
            </strong>
          </article>
          <article className="metric">
            <p>Open positions</p>
            <strong>{ledger?.open_positions ?? 0}</strong>
          </article>
          <article className="metric">
            <p>{isDualConfig ? 'Loss cap (global / desks)' : 'Max loss cap'}</p>
            <strong>
              {isDualConfig
                ? `${money.format(globalLossCap)} / ${money.format(deskLossCap)}`
                : money.format(globalLossCap || deskLossCap || 0)}
            </strong>
            {isDualConfig && globalLossCap > 0 && globalLossCap < deskLossCap && (
              <span className="subtle" style={{ display: 'block', fontSize: '0.75rem', marginTop: 4 }}>
                Global cap binds first — raise Risk → max intraday loss to match desks.
              </span>
            )}
          </article>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="eyebrow">ALL-DAY SESSION</p>
            <h3>Curated list, agent auto-pick, or dual desk</h3>
          </div>
          <span className={`live-pill ${sessionActive ? 'is-live' : ''}`}>
            {sessionActive ? 'SESSION LIVE' : 'IDLE'}
          </span>
        </div>
        <p className="subtle">
          Follows NSE hours: <b>09:00</b> pre-market analysis → <b>09:15</b> live trading → <b>15:30</b> close.
          Agent polls for correct entry timing, exits on target/stop, books profit, and re-enters all day.
        </p>

        {nseInfo && (
          <div className="app-alert" style={{ marginTop: 10, marginBottom: 0 }}>
            <p className="app-alert-message">
              <b>{nseInfo.ist_time} IST</b> · {nseInfo.label}
              {nseInfo.minutes_to_open > 0 && (
                <> · Trading opens in <b>{nseInfo.minutes_to_open} min</b></>
              )}
              {nseInfo.next_transition && (
                <> · Next: {nseInfo.next_transition.event} at {nseInfo.next_transition.at}</>
              )}
            </p>
          </div>
        )}

        <div className="profit-profile-panel" style={{ marginTop: 14 }}>
          <p className="eyebrow">PROFIT PROFILE</p>

          {homeRunRec && (
            <div
              className={`home-run-rec-banner home-run-rec-${homeRunRec.recommendation}${homeRunRec.aligned ? ' is-aligned' : ''}`}
              style={{ marginTop: 8, marginBottom: 12 }}
            >
              <div className="home-run-rec-head">
                <strong>{homeRunRec.headline}</strong>
                <span className="home-run-rec-score">Score {homeRunRec.score}/100</span>
              </div>
              <p className="subtle" style={{ margin: '6px 0' }}>{homeRunRec.action}</p>
              {homeRunRec.reasons?.length > 0 && (
                <ul className="home-run-rec-list">
                  {homeRunRec.reasons.map(r => <li key={r}>{r}</li>)}
                </ul>
              )}
              {homeRunRec.cautions?.length > 0 && (
                <ul className="home-run-rec-list home-run-rec-cautions">
                  {homeRunRec.cautions.map(c => <li key={c}>{c}</li>)}
                </ul>
              )}
              {homeRunRec.signals && (
                <p className="subtle home-run-rec-signals">
                  Breadth {homeRunRec.signals.breadth_pct}% · {homeRunRec.signals.small_high_atr_count} small ATR≥3.5%
                  · avg ATR {homeRunRec.signals.avg_atr_top_pct}% · {homeRunRec.signals.session_label}
                </p>
              )}
              {!sessionActive && (homeRunRec.recommendation === 'home_run' || homeRunRec.recommendation === 'consider_home_run')
                && activeProfitProfile !== 'home_run' && (
                <button
                  type="button"
                  className="primary"
                  style={{ marginTop: 10 }}
                  disabled={busy === 'profit-profile'}
                  onClick={() => applyProfitProfile('home_run')}
                >
                  {busy === 'profit-profile' ? 'Applying…' : 'Apply Home run profile'}
                </button>
              )}
              {!sessionActive && homeRunRec.recommendation === 'avoid_home_run' && activeProfitProfile === 'home_run' && (
                <button
                  type="button"
                  className="ghost"
                  style={{ marginTop: 10 }}
                  disabled={busy === 'profit-profile'}
                  onClick={() => applyProfitProfile('conservative')}
                >
                  Switch to Conservative
                </button>
              )}
            </div>
          )}

          <p className="subtle" style={{ marginTop: 4, marginBottom: 10 }}>
            One-click risk/target preset. Conservative for steady ₹15–30k days; Home run for ₹150k ceiling on trend days.
          </p>
          <label className="refresh-toggle" style={{ display: 'block', marginBottom: 10 }}>
            <input
              type="checkbox"
              checked={ap.auto_home_run_enabled !== false}
              disabled={sessionActive || busy === 'profit-profile'}
              onChange={e => patchConfig({ autopilot: { ...ap, auto_home_run_enabled: e.target.checked } })}
            />
            Auto-switch Home run for agent auto-pick when score ≥ 65 (revert below 45 · 20m cooldown)
          </label>
          {profitProfiles?.auto_profile_state?.last_profile && (
            <p className="subtle" style={{ fontSize: '0.8rem', marginBottom: 10 }}>
              Last auto switch: {profitProfiles.auto_profile_state.last_profile} at score {profitProfiles.auto_profile_state.last_score}
            </p>
          )}
          <div className="profit-profile-grid">
            {(profitProfileOptions.length ? profitProfileOptions : [
              { id: 'conservative', label: 'Conservative', tagline: '₹15–30k typical days', description: 'Tighter risk', estimate: { typical_net_inr: 20000 } },
              { id: 'home_run', label: 'Home run', tagline: '₹150k ceiling', description: 'Aggressive sizing', estimate: { typical_net_inr: 140000 } },
            ]).map(profile => {
              const active = activeProfitProfile === profile.id
              return (
                <button
                  key={profile.id}
                  type="button"
                  className={`profit-profile-card${active ? ' is-active' : ''}`}
                  disabled={sessionActive || busy === 'profit-profile'}
                  onClick={() => { if (!active) applyProfitProfile(profile.id) }}
                >
                  <span className="profit-profile-card-label">{profile.label}</span>
                  <span className="profit-profile-card-tagline">{profile.tagline}</span>
                  <span className="subtle profit-profile-card-desc">{profile.description}</span>
                  {profile.estimate?.typical_net_inr != null && (
                    <span className="profit-profile-card-est">
                      Est. net/day ~{money.format(profile.estimate.typical_net_inr)}
                    </span>
                  )}
                  {active && <span className="profit-profile-active-pill">Active</span>}
                </button>
              )
            })}
          </div>
          {profitProfiles?.applied && (
            <p className="subtle" style={{ marginTop: 8, fontSize: '0.8rem' }}>
              Applied: max position {money.format(profitProfiles.applied.max_position_inr || risk.max_position_inr || 0)}
              {' · '}risk/trade {money.format(profitProfiles.applied.risk_per_trade_inr || ap.risk_per_trade_inr || 0)}
              {' · '}home-run target {(profitProfiles.applied.home_run_target_pct || ap.home_run_target_pct || 0)}%
            </p>
          )}
        </div>

        <div className="autopilot-controls" style={{ marginTop: 10 }}>
          <label className="refresh-toggle">
            <input type="radio" name="pick-mode" checked={pickMode === 'curated_list'}
              onChange={() => setPickMode('curated_list')} disabled={sessionActive} />
            My stocks (1–20)
          </label>
          <label className="refresh-toggle">
            <input type="radio" name="pick-mode" checked={pickMode === 'agent_auto'}
              onChange={() => setPickMode('agent_auto')} disabled={sessionActive} />
            Agent picks (Nifty 500)
          </label>
          <label className="refresh-toggle">
            <input type="radio" name="pick-mode" checked={pickMode === 'dual_desk'}
              onChange={() => {
                setPickMode('dual_desk')
                if (!curatedSymbols.length) {
                  const saved = savedCuratedSymbolsFromConfig()
                  if (saved.length) setCuratedSymbols(saved)
                }
              }}
              disabled={sessionActive} />
            Dual desk (both in parallel)
          </label>
        </div>

        {(pickMode === 'curated_list' || pickMode === 'dual_desk') && (
          <div style={{ marginTop: 12 }}>
            <SymbolSearchField
              inputId="autopilot-symbol-search"
              value={symbolSearch.query}
              onChange={symbolSearch.onQueryChange}
              onPick={addCuratedSymbol}
              searching={symbolSearch.searching}
              suggestions={symbolSearch.suggestions}
              placeholder={`Search & add stock — e.g. BIKEWO.NSE (up to ${CURATED_SYMBOLS_MAX})`}
            />
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8, alignItems: 'center' }}>
              {curatedSymbols.map(sym => (
                <button
                  key={sym}
                  type="button"
                  className="ghost"
                  disabled={sessionActive}
                  onClick={() => removeCuratedSymbol(sym)}
                  title="Remove"
                >
                  {sym} ×
                </button>
              ))}
              {curatedSymbols.length === 0 && (
                <span className="subtle">No stocks selected yet.</span>
              )}
            </div>
            <div className="row-actions" style={{ marginTop: 8, gap: 8, flexWrap: 'wrap' }}>
              <button type="button" className="ghost" disabled={sessionActive || busy === 'save-list' || curatedSymbols.length < 1}
                onClick={saveCuratedList}>
                {busy === 'save-list' ? 'Saving…' : 'Save list'}
              </button>
              <button type="button" className="ghost" disabled={curatedSymbols.length < 1} onClick={copyCuratedList}>
                Copy all
              </button>
              <button type="button" className="ghost" disabled={sessionActive || busy === 'paste-list'} onClick={pasteCuratedList}>
                Paste list
              </button>
              <span className="subtle">{curatedSymbols.length}/{CURATED_SYMBOLS_MAX} saved to config when you click Save list</span>
            </div>
          </div>
        )}

        {pickMode === 'dual_desk' ? (
          <>
            <p className="eyebrow" style={{ marginTop: 12 }}>AI AUTO DESK</p>
            <div className="buy-grid">
              <label className="settings-field">
                Agent max spend (₹)
                <input type="number" min={1000} step={5000} value={agentMaxSpend}
                  disabled={sessionActive}
                  onChange={e => setAgentMaxSpend(Number(e.target.value))} />
              </label>
              <label className="settings-field">
                Agent max profit (₹)
                <input type="number" min={0} step={1000} value={agentMaxProfit}
                  disabled={sessionActive}
                  onChange={e => setAgentMaxProfit(Number(e.target.value))} />
              </label>
              <label className="settings-field">
                Agent max loss (₹)
                <input type="number" min={0} step={500} value={agentMaxLoss}
                  disabled={sessionActive}
                  onChange={e => setAgentMaxLoss(Number(e.target.value))} />
              </label>
              <label className="settings-field">
                Agent max positions
                <input type="number" min={1} max={10} value={agentMaxConcurrent}
                  disabled={sessionActive}
                  onChange={e => setAgentMaxConcurrent(Number(e.target.value))} />
              </label>
            </div>
            <p className="eyebrow" style={{ marginTop: 12 }}>CURATED DESK</p>
            <div className="buy-grid">
              <label className="settings-field">
                Curated max spend (₹)
                <input type="number" min={1000} step={5000} value={curatedMaxSpend}
                  disabled={sessionActive}
                  onChange={e => setCuratedMaxSpend(Number(e.target.value))} />
              </label>
              <label className="settings-field">
                Curated max profit (₹)
                <input type="number" min={0} step={1000} value={curatedMaxProfit}
                  disabled={sessionActive}
                  onChange={e => setCuratedMaxProfit(Number(e.target.value))} />
              </label>
              <label className="settings-field">
                Curated max loss (₹)
                <input type="number" min={0} step={500} value={curatedMaxLoss}
                  disabled={sessionActive}
                  onChange={e => setCuratedMaxLoss(Number(e.target.value))} />
              </label>
              <label className="settings-field">
                Curated max positions
                <input type="number" min={1} max={10} value={curatedMaxConcurrent}
                  disabled={sessionActive}
                  onChange={e => setCuratedMaxConcurrent(Number(e.target.value))} />
              </label>
            </div>
          </>
        ) : (
        <div className="buy-grid" style={{ marginTop: 12 }}>
          <label className="settings-field">
            Max spend (₹)
            <input type="number" min={1000} step={5000} value={maxSpend}
              disabled={sessionActive}
              onChange={e => setMaxSpend(Number(e.target.value))} />
          </label>
          <label className="settings-field">
            Max profit (₹)
            <input type="number" min={0} step={1000} value={maxProfit}
              disabled={sessionActive}
              onChange={e => setMaxProfit(Number(e.target.value))} />
          </label>
          <label className="settings-field">
            Max loss (₹)
            <input type="number" min={0} step={500} value={maxLoss}
              disabled={sessionActive}
              onChange={e => setMaxLoss(Number(e.target.value))} />
          </label>
          <label className="settings-field">
            Max concurrent positions
            <input type="number" min={1} max={10} value={maxConcurrent}
              disabled={sessionActive}
              onChange={e => setMaxConcurrent(Number(e.target.value))} />
          </label>
        </div>
        )}

        <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {!(sessionActive || stopExistingSessionError) ? (
            <button type="button" className="primary" disabled={!!busy} onClick={startSession}>
              {pickMode === 'dual_desk' ? 'Start dual desk' : 'Start all-day session'}
            </button>
          ) : (
            <>
              <button type="button" className="primary" disabled={!!busy} onClick={() => stopSession()}>
                Stop all desks
              </button>
              {dualMode && activeSessions.map(desk => (
                <button
                  key={desk.id}
                  type="button"
                  className="ghost"
                  disabled={!!busy}
                  onClick={() => stopSession(desk.id)}
                >
                  Stop {desk.pick_mode === 'agent_auto' ? 'AI desk' : 'curated desk'}
                </button>
              ))}
            </>
          )}
          <button type="button" className="ghost" disabled={!!busy} onClick={runAutopilot}>
            Run cycle now
          </button>
        </div>
        {statusMsg && !error && (
          <p className="subtle" style={{ marginTop: 8, color: 'var(--accent, #2ecc71)' }}>{statusMsg}</p>
        )}
        {error && pickMode === 'dual_desk' && (
          <div style={{ marginTop: 8, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <p className="down" style={{ margin: 0 }}>{error}</p>
            {stopExistingSessionError && !sessionActive && (
              <button type="button" className="primary" disabled={!!busy} onClick={() => stopSession()}>
                Stop all desks
              </button>
            )}
          </div>
        )}
        {error && pickMode !== 'dual_desk' && (
          <p className="down" style={{ marginTop: 8 }}>{error}</p>
        )}

        {activeSessions.length > 0 && (
          <div style={{ marginTop: 10 }}>
            {activeSessions.map(desk => {
              const pnl = deskPnl(desk)
              return (
              <p key={desk.id} className="subtle">
                <b>{desk.pick_mode === 'agent_auto' ? 'AI auto-pick' : 'Curated list'}</b>
                {' · '}
                Started {desk.started_at ? new Date(desk.started_at).toLocaleString('en-IN') : '—'}
                {' · '}
                Net P&amp;L:{' '}
                <strong className={pnl.net >= 0 ? 'up' : 'down'}>
                  {money.format(pnl.net)}
                </strong>
                {' · '}
                Realized {money.format(pnl.realized)}
                {' · '}
                Unrealized{' '}
                <strong className={pnl.unrealized >= 0 ? 'up' : 'down'}>
                  {money.format(pnl.unrealized)}
                </strong>
                {desk.caps && (
                  <> · Budget {money.format(desk.caps.max_daily_notional_inr)}</>
                )}
                {desk.pick_mode === 'curated_list' && desk.curated_symbols?.length > 0 && (
                  <> · {desk.curated_symbols.join(', ')}</>
                )}
                {' · '}
                {desk.cycle_count ?? desk.cycles?.length ?? 0} cycles
              </p>
              )
            })}
            {macSleepGuard?.active && (
              <p className="subtle">
                Mac awake until <b>{macSleepGuard.wake_until_ist}</b> IST
              </p>
            )}
          </div>
        )}

        {activeSession && activeSessions.length === 0 && (
          <p className="subtle" style={{ marginTop: 10 }}>
            Mode: <b>{activeSession.pick_mode === 'agent_auto' ? 'Agent auto-pick' : 'Curated list'}</b>
            {' · '}
            Started {activeSession.started_at ? new Date(activeSession.started_at).toLocaleString('en-IN') : '—'}
            {' · '}
            Session P&amp;L:{' '}
            <strong className={sessionPnl >= 0 ? 'up' : 'down'}>{money.format(sessionPnl)}</strong>
            {activeSession.caps && (
              <> · Caps spend {money.format(activeSession.caps.max_daily_notional_inr)}</>
            )}
            {macSleepGuard?.active && (
              <> · Mac awake until <b>{macSleepGuard.wake_until_ist}</b> IST</>
            )}
          </p>
        )}

        {visibleSessionTrades.length > 0 && (
          <>
            <p className="eyebrow" style={{ marginTop: 16 }}>EXECUTED TRADES</p>
            <ul className="reason-list compact">
              {visibleSessionTrades.slice(0, 60).map(row => (
                <li key={row.id}>
                  <span>{row.side?.toUpperCase()} {row.symbol}</span>
                  {' · '}
                  {row.quantity} @ {money.format(row.price || 0)}
                  {row.pnl_inr != null && (
                    <span className={row.pnl_inr >= 0 ? 'up' : 'down'}>
                      {' · P&L '}{money.format(row.pnl_inr)}
                    </span>
                  )}
                  {row.reason && <span className="subtle"> · {row.reason}</span>}
                </li>
              ))}
            </ul>
          </>
        )}

        {!sessionActive && session?.history?.[0] && (
          <p className="subtle" style={{ marginTop: 10 }}>
            Last session: {session.history[0].completion_reason || session.history[0].status}
            {' · '}
            P&amp;L {money.format(session.history[0].realized_pnl_inr || 0)}
            {' · '}
            {session.history[0].cycle_count ?? session.history[0].cycles?.length ?? 0} cycles logged
          </p>
        )}
        {sessionActive && session?.nse?.phase === 'post_close' && (
          <p className="subtle warn" style={{ marginTop: 10 }}>
            Market closed (15:30 IST) — session auto-stops on the next scheduler tick.
          </p>
        )}
        {sessionActive && sessionCycleCount > 0 && (
          <p className="subtle" style={{ marginTop: 6 }}>
            {sessionCycleCount} scheduler cycles logged today
          </p>
        )}
      </section>

      <SessionReportsPanel
        sessions={sessionReports}
        selectedId={selectedReportId || eodReport?.session_id || ''}
        busy={busy}
        onSelect={openSessionReport}
        onDownloadPdf={downloadSessionReportPdf}
      />

      {eodReport?.summary && (
        <section className="panel session-eod-report">
          <div className="panel-head">
            <div>
              <p className="eyebrow">EOD REPORT</p>
              <h3>Session summary &amp; post-mortem</h3>
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {eodReport.session_id && (
                <button
                  type="button"
                  className="ghost"
                  disabled={!!busy}
                  onClick={() => downloadSessionReportPdf(eodReport.session_id)}
                >
                  Download PDF
                </button>
              )}
              {eodReport.markdown && (
                <button
                  type="button"
                  className="ghost"
                  onClick={() => navigator.clipboard?.writeText(eodReport.markdown)}
                >
                  Copy markdown
                </button>
              )}
              <button type="button" className="ghost" disabled={!!busy} onClick={refresh}>Refresh</button>
            </div>
          </div>
          <div className="session-eod-stats">
            <p>
              P&amp;L{' '}
              <strong className={(eodReport.summary.realized_pnl_inr || 0) >= 0 ? 'up' : 'down'}>
                {money.format(eodReport.summary.realized_pnl_inr || 0)}
              </strong>
              {' · '}
              Win rate <b>{eodReport.summary.win_rate_pct ?? '—'}%</b>
              {' · '}
              {eodReport.summary.closed_trades ?? 0} closes
              {' · '}
              {eodReport.summary.wins ?? 0}W / {eodReport.summary.losses ?? 0}L
            </p>
            {eodReport.summary.best_symbol && (
              <p className="subtle">
                Best: <b>{eodReport.summary.best_symbol.symbol}</b> {money.format(eodReport.summary.best_symbol.pnl_inr || 0)}
                {eodReport.summary.worst_symbol && eodReport.summary.worst_symbol.symbol !== eodReport.summary.best_symbol.symbol && (
                  <> · Worst: <b>{eodReport.summary.worst_symbol.symbol}</b> {money.format(eodReport.summary.worst_symbol.pnl_inr || 0)}</>
                )}
              </p>
            )}
            {eodReport.postmortem?.executive_summary && (
              <p style={{ marginTop: 8 }}>{eodReport.postmortem.executive_summary}</p>
            )}
            {eodReport.rag?.session_rag_id && (
              <p className="subtle" style={{ marginTop: 6 }}>
                Saved to RAG for next session (id {String(eodReport.rag.session_rag_id).slice(0, 8)}…)
              </p>
            )}
          </div>
          {eodReport.markdown && (
            <pre className="session-eod-markdown">{eodReport.markdown}</pre>
          )}
        </section>
      )}

      <TradePlanPanel
        intradayRules={intradayRules}
        swingRules={swingRules}
        rows={planRows}
        loading={planLoading}
        sourceLabel={planSourceLabel}
      />

      {(sessionEvents.length > 0 || latestAudit.length > 0) && (
        <section className="panel session-history-panel">
          <div className="panel-head">
            <div>
              <p className="eyebrow">DETAILED HISTORY</p>
              <h3>What the system tried each cycle</h3>
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <button type="button" className="ghost" disabled={!!busy} onClick={refresh}>Refresh log</button>
              <label className="subtle" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                Keep last
                <select
                  value={logRetention}
                  disabled={!!busy}
                  onChange={e => setLogRetention(e.target.value)}
                >
                  <option value="1h">1 hour</option>
                  <option value="12h">12 hours</option>
                  <option value="1d">1 day</option>
                  <option value="7d">7 days</option>
                </select>
              </label>
              <button type="button" className="ghost" disabled={!!busy} onClick={clearSessionLog}>
                Clear older logs
              </button>
            </div>
          </div>
          <p className="subtle">
            Every scheduler tick, guard exit, pick attempt, skip, and RAG lookup is recorded.
            Click an event to expand full JSON detail.
          </p>

          {latestAudit.length > 0 && (
            <>
              <p className="eyebrow" style={{ marginTop: 14 }}>LATEST CYCLE — SYMBOL DECISIONS</p>
              <div className="session-audit-table-wrap">
                <table className="session-audit-table">
                  <thead>
                    <tr>
                      <th>Symbol</th>
                      <th>Decision</th>
                      <th>Score</th>
                      <th>Why</th>
                    </tr>
                  </thead>
                  <tbody>
                    {latestAudit.map(row => (
                      <tr key={row.symbol} className={`audit-${row.decision}`}>
                        <td><b>{row.symbol}</b></td>
                        <td>{row.decision}</td>
                        <td>{row.pick_score ?? row.composite_score ?? '—'}</td>
                        <td className="subtle">{row.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {latestCycle?.pick_result?.budget && (
                <p className="subtle" style={{ marginTop: 8 }}>
                  Budget left ₹{(latestCycle.pick_result.budget.remaining_budget_inr || 0).toLocaleString('en-IN')}
                  {' · '}
                  Slots {latestCycle.pick_result.budget.position_slots ?? '—'}
                  {' · '}
                  Orders left {latestCycle.pick_result.budget.orders_left ?? '—'}
                </p>
              )}
            </>
          )}

          {sessionEvents.length > 0 && (
            <>
              <p className="eyebrow" style={{ marginTop: 14 }}>EVENT TIMELINE ({sessionEvents.length})</p>
              <ul className="reason-list compact session-event-list">
                {sessionEvents.slice(0, 120).map(evt => (
                  <SessionEventRow
                    key={evt.id}
                    event={evt}
                    expanded={expandedEventId === evt.id}
                    onToggle={() => setExpandedEventId(expandedEventId === evt.id ? null : evt.id)}
                  />
                ))}
              </ul>
            </>
          )}

          {sessionTrades.filter(r => r.side === 'buy_skipped').length > 0 && (
            <>
              <p className="eyebrow" style={{ marginTop: 14 }}>SKIPPED BUY ATTEMPTS</p>
              <ul className="reason-list compact">
                {sessionTrades.filter(r => r.side === 'buy_skipped').slice(0, 30).map(row => (
                  <li key={row.id}>
                    <span className="down">SKIP {row.symbol}</span>
                    {' · '}
                    {row.reason}
                    {row.detail?.timing && (
                      <span className="subtle"> · timing gate</span>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      )}

      <section className="panel">
        <div className="panel-head">
          <div><p className="eyebrow">RISK GUARDRAILS</p><h3>Auto-mode loss prevention</h3></div>
        </div>
        <p className="subtle">Applied to agent trades, autopilot, and live MIS. Stop/target + EOD square-off run each scheduler tick.</p>
        <div className="buy-grid" style={{ marginTop: 12 }}>
          <label className="settings-field">
            Max daily loss (₹)
            <input type="number" min={0} step={500} value={risk.max_intraday_loss_inr ?? 5000}
              onChange={e => patchRisk('max_intraday_loss_inr', Number(e.target.value))} />
          </label>
          <label className="settings-field">
            Max unrealized loss (₹)
            <input type="number" min={0} step={500} value={risk.max_unrealized_loss_inr ?? 3000}
              onChange={e => patchRisk('max_unrealized_loss_inr', Number(e.target.value))} />
          </label>
          <label className="settings-field">
            Max daily profit lock (₹)
            <input type="number" min={0} step={500} value={risk.max_profit_inr ?? 0}
              onChange={e => patchRisk('max_profit_inr', Number(e.target.value))} />
          </label>
          <label className="settings-field">
            Max per-order size (₹)
            <input type="number" min={0} step={1000} value={risk.max_position_inr ?? 50000}
              onChange={e => patchRisk('max_position_inr', Number(e.target.value))} />
          </label>
          <label className="settings-field">
            Max daily buy bucket (₹)
            <input type="number" min={0} step={5000} value={risk.max_daily_notional_inr ?? 100000}
              onChange={e => patchRisk('max_daily_notional_inr', Number(e.target.value))} />
          </label>
          <label className="settings-field">
            Max orders / day
            <input type="number" min={1} max={50} value={risk.max_orders_per_day ?? 5}
              onChange={e => patchRisk('max_orders_per_day', Number(e.target.value))} />
          </label>
          <label className="settings-field">
            Max open positions
            <input type="number" min={1} max={20} value={risk.max_open_positions ?? 3}
              onChange={e => patchRisk('max_open_positions', Number(e.target.value))} />
          </label>
          <label className="settings-field">
            Agent min composite
            <input type="number" min={0} max={100} step={1} value={risk.agent_min_composite ?? 55}
              onChange={e => patchRisk('agent_min_composite', Number(e.target.value))} />
          </label>
          <label className="settings-field">
            Stop % (auto exit)
            <input type="number" min={0.1} max={10} step={0.1} value={risk.default_stop_pct ?? ap.stop_pct ?? 0.75}
              onChange={e => patchRisk('default_stop_pct', Number(e.target.value))} />
          </label>
          <label className="settings-field">
            Target % (auto exit)
            <input type="number" min={0.1} max={20} step={0.1} value={risk.default_target_pct ?? ap.target_pct ?? 1.5}
              onChange={e => patchRisk('default_target_pct', Number(e.target.value))} />
          </label>
        </div>
        <label className="refresh-toggle" style={{ marginTop: 10 }}>
          <input type="checkbox" checked={risk.auto_square_off_enabled !== false}
            onChange={e => patchRisk('auto_square_off_enabled', e.target.checked)} />
          Auto stop/target + EOD square-off
        </label>
        <label className="refresh-toggle">
          <input type="checkbox" checked={risk.halt_new_buys_on_profit !== false}
            onChange={e => patchRisk('halt_new_buys_on_profit', e.target.checked)} />
          Halt new buys when profit cap hit
        </label>
      </section>

      <section className="panel">
        <div className="panel-head">
          <div><p className="eyebrow">MORNING SCAN</p><h3>Nifty 500 → RAG (agent ready)</h3></div>
          <button type="button" className="ghost" disabled={!!busy} onClick={runMorningScan}>Run now</button>
        </div>
        <p className="subtle">
          Pre-market job scores all 500 names, saves locally, and feeds Chroma for the research desk.
          Scheduler runs ~9:00 IST when autopilot is enabled.
        </p>
        <label className="refresh-toggle">
          <input
            type="checkbox"
            checked={ap.morning_scan_enabled !== false}
            onChange={e => patchConfig({ autopilot: { ...ap, morning_scan_enabled: e.target.checked } })}
          />
          Enable morning scan scheduler
        </label>
        {morningScan && (
          <p className="subtle" style={{ marginTop: 8 }}>
            Last: {morningScan.trade_date_ist || '—'} · {morningScan.scored ?? '—'} scored ·
            RAG chunks {morningScan.rag_chunks?.batches ?? morningScan.rag_chunks ?? '—'}
            {(morningScan.top_bullish || []).length > 0 && (
              <> · Top: {(morningScan.top_bullish || []).map(t => t.symbol).slice(0, 3).join(', ')}</>
            )}
          </p>
        )}
      </section>

      <section className="panel">
        <div className="panel-head">
          <div><p className="eyebrow">QUANT PIPELINE</p><h3>Layer 1 triggers + LLM digest</h3></div>
          <button type="button" className="ghost" disabled={!!busy} onClick={runQuantPipeline}>Run pipeline</button>
        </div>
        <p className="subtle">
          Scans Nifty 500 for deterministic triggers (Agents 0–6), optionally runs LLM synthesis (Agents 1/2/7),
          and caches a daily digest for Auto Pick conviction gates.
        </p>
        <label className="refresh-toggle">
          <input
            type="checkbox"
            checked={ap.quant_layer_enabled !== false}
            onChange={e => patchConfig({ autopilot: { ...ap, quant_layer_enabled: e.target.checked } })}
          />
          Enable quant layer (morning scan merge)
        </label>
        <label className="refresh-toggle">
          <input
            type="checkbox"
            checked={ap.quant_llm_synthesis_enabled === true}
            onChange={e => patchConfig({ autopilot: { ...ap, quant_llm_synthesis_enabled: e.target.checked } })}
          />
          LLM conviction veto on Auto Pick
        </label>
        <div style={{ marginTop: 8, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button type="button" className="ghost" disabled={!!busy} onClick={runDailyUniverse}>
            Daily universe job
          </button>
          <button type="button" className="ghost" disabled={!!busy} onClick={runPreLiveHygiene}>
            Pre-live hygiene
          </button>
          <button type="button" className="ghost danger" disabled={!!busy} onClick={resetLearningRag}>
            Reset RAG / learning
          </button>
        </div>
        {quantDigest && (
          <p className="subtle" style={{ marginTop: 8 }}>
            Regime: {quantDigest.regime?.regime || quantDigest.regime?.label || '—'}
            {' · '}
            Triggered {quantDigest.quant_summary?.triggered_count ?? '—'}
            {' · '}
            Shortlist {quantDigest.quant_summary?.shortlist_count ?? (quantDigest.ranked || []).length}
            {(quantDigest.ranked || []).length > 0 && (
              <> · Top: {(quantDigest.ranked || []).slice(0, 3).map(r => r.symbol).join(', ')}</>
            )}
          </p>
        )}
      </section>

      <section className="panel">
        <div className="panel-head">
          <div><p className="eyebrow">TIMING INTEL</p><h3>Session patterns (not HFT speed)</h3></div>
          <button type="button" className="ghost" disabled={!!busy} onClick={learnTiming}>Learn patterns</button>
        </div>
        <p className="subtle">
          Pro desks may see NSE/BSE ticks 1–5s earlier via co-location. We cannot replicate that on retail feeds.
          Instead we learn gap/weekday/session patterns from history, gate auto-trades to favorable IST windows,
          and enter <b>pre-emptively</b> when momentum + patterns suggest the move continues before our delayed feed catches up.
        </p>
        {timing && (
          <p className="subtle" style={{ marginTop: 8 }}>
            Now: <b>{timing.current_window?.label || '—'}</b>
            {timing.current_window?.ist_time ? ` (${timing.current_window.ist_time} IST)` : ''}
            {' · '}
            Auto-trade {timing.auto_trade_allowed_now ? 'allowed' : 'blocked'}
            {timing.gate_reason ? ` (${timing.gate_reason})` : ''}
            {' · '}
            Profiles learned: {timing.profiles_learned ?? 0}
            {timing.latency_compensation?.latency_budget && (
              <>
                {' · '}
                Feed delay budget: <b>{timing.latency_compensation.latency_budget.budget_seconds}s</b>
                {timing.latency_compensation.latency_budget.transport
                  ? ` (${timing.latency_compensation.latency_budget.transport})`
                  : ''}
              </>
            )}
          </p>
        )}
        <label className="refresh-toggle">
          <input
            type="checkbox"
            checked={ap.timing_intel_enabled !== false}
            onChange={e => patchConfig({ autopilot: { ...ap, timing_intel_enabled: e.target.checked } })}
          />
          Enable timing intelligence
        </label>
        <label className="refresh-toggle">
          <input
            type="checkbox"
            checked={ap.timing_gate_auto_trades !== false}
            onChange={e => patchConfig({ autopilot: { ...ap, timing_gate_auto_trades: e.target.checked } })}
          />
          Block auto-trades outside favorable windows (pre-open / closing auction)
        </label>
        <label className="refresh-toggle">
          <input
            type="checkbox"
            checked={ap.fast_poll_open_window !== false}
            onChange={e => patchConfig({ autopilot: { ...ap, fast_poll_open_window: e.target.checked } })}
          />
          Faster poll during open drive (30s vs default)
        </label>
        <label className="refresh-toggle">
          <input
            type="checkbox"
            checked={!!ap.timing_strict_symbol}
            onChange={e => patchConfig({ autopilot: { ...ap, timing_strict_symbol: e.target.checked } })}
          />
          Strict per-symbol windows (requires Learn patterns first)
        </label>
        <label className="refresh-toggle">
          <input
            type="checkbox"
            checked={ap.latency_compensation_enabled !== false}
            onChange={e => patchConfig({ autopilot: { ...ap, latency_compensation_enabled: e.target.checked } })}
          />
          Enable latency compensation (pre-emptive entry when patterns align)
        </label>
        <label className="refresh-toggle">
          <input
            type="checkbox"
            checked={!!ap.latency_require_preemptive}
            onChange={e => patchConfig({ autopilot: { ...ap, latency_require_preemptive: e.target.checked } })}
          />
          Require strong pattern before any auto-buy (strict mode)
        </label>
      </section>

      <section className="panel">
        <div className="panel-head">
          <div><p className="eyebrow">LTP STREAM</p><h3>Broker WebSocket / fast poll</h3></div>
          <button type="button" className="ghost" disabled={!!busy} onClick={syncLtpStream}>Sync symbols</button>
        </div>
        <p className="subtle">
          Zerodha uses KiteTicker WebSocket (true tick LTP). Groww/FYERS use 3s REST poll into the same cache.
          Without broker keys, Yahoo/NSE poll (~15s) feeds the same WebSocket to LivePulse on the Swing desk.
        </p>
        {ltpStream && (
          <p className="subtle" style={{ marginTop: 8 }}>
            Broker: <b>{ltpStream.broker || '—'}</b>
            {' · '}
            Transport: <b>{ltpStream.transport || 'none'}</b>
            {ltpStream.stream?.connected != null && (
              <> · WS {ltpStream.stream.connected ? 'connected' : 'disconnected'}</>
            )}
            {' · '}
            Cache: {ltpStream.cache?.fresh_60s ?? 0}/{ltpStream.cache?.symbols ?? 0} fresh
            {ltpStream.gateway_mode && ' · gateway mode (stream runs on gateway host)'}
          </p>
        )}
        <label className="refresh-toggle">
          <input
            type="checkbox"
            checked={ap.ltp_stream_enabled !== false}
            onChange={e => patchConfig({ autopilot: { ...ap, ltp_stream_enabled: e.target.checked } })}
          />
          Enable LTP stream (restart API to apply)
        </label>
        <label className="settings-field" style={{ marginTop: 8 }}>
          REST poll interval (Groww/FYERS, seconds)
          <input
            type="number"
            min={1}
            max={30}
            step={1}
            value={ap.ltp_poll_seconds ?? 3}
            onChange={e => patchConfig({ autopilot: { ...ap, ltp_poll_seconds: Number(e.target.value) } })}
          />
        </label>
      </section>

      <section className="panel">
        <div className="panel-head">
          <div><p className="eyebrow">AUTOPILOT</p><h3>Phases C + D — watchlist &amp; paper bot</h3></div>
        </div>
        <p className="subtle">Watchlist used when agent <b>Auto-pick</b> is OFF (given-stocks mode).</p>
        <label className="refresh-toggle">
          <input
            type="checkbox"
            checked={!!ap.enabled}
            onChange={e => patchConfig({ autopilot: { ...ap, enabled: e.target.checked } })}
          />
          Enable scheduler (background poll)
        </label>
        <label className="refresh-toggle">
          <input
            type="checkbox"
            checked={!!ap.live_autopilot}
            onChange={e => patchConfig({ autopilot: { ...ap, live_autopilot: e.target.checked } })}
          />
          Live autopilot entries (requires arm + broker)
        </label>
        <label className="refresh-toggle">
          <input
            type="checkbox"
            checked={ap.use_morning_scan_candidates !== false}
            onChange={e => patchConfig({ autopilot: { ...ap, use_morning_scan_candidates: e.target.checked } })}
          />
          Include morning-scan leaders in autopilot candidates
        </label>
        <label className="refresh-toggle">
          <input
            type="checkbox"
            checked={config.reconcile_enabled !== false}
            onChange={e => patchConfig({ reconcile_enabled: e.target.checked })}
          />
          Broker ↔ shadow reconcile each tick
        </label>
        <label className="refresh-toggle">
          <input
            type="checkbox"
            checked={config.margin_check_enabled !== false}
            onChange={e => patchConfig({ margin_check_enabled: e.target.checked })}
          />
          Margin pre-check before live buys
        </label>
        <label className="refresh-toggle">
          <input
            type="checkbox"
            checked={risk.place_sl_m_at_entry !== false}
            onChange={e => patchRisk('place_sl_m_at_entry', e.target.checked)}
          />
          Place broker SL-M after confirmed MIS buy
        </label>
        <label className="refresh-toggle">
          <input
            type="checkbox"
            checked={ap.watchlist_agent !== false}
            onChange={e => patchConfig({ autopilot: { ...ap, watchlist_agent: e.target.checked } })}
          />
          Watchlist agent (alerts only)
        </label>
        <label className="refresh-toggle">
          <input
            type="checkbox"
            checked={!!ap.intraday_sim}
            onChange={e => patchConfig({ autopilot: { ...ap, intraday_sim: e.target.checked } })}
          />
          Intraday paper sim (Phase B)
        </label>
        <label className="settings-field" style={{ marginTop: 10 }}>
          Active symbol (intraday sim)
          <input
            value={ap.active_symbol || ''}
            onChange={e => patchConfig({ autopilot: { ...ap, active_symbol: e.target.value.toUpperCase() } })}
            placeholder="RELIANCE.NSE"
          />
        </label>
        <label className="settings-field">
          Watchlist (comma-separated)
          <input
            value={watchInput}
            onChange={e => setWatchInput(e.target.value)}
            onBlur={() => patchConfig({
              watchlist: watchInput.split(/[,\s]+/).map(s => s.trim().toUpperCase()).filter(Boolean),
            })}
            placeholder="RELIANCE.NSE, TCS.NSE"
          />
        </label>
        <div style={{ marginTop: 10, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button type="button" className="primary" disabled={!!busy} onClick={runAutopilot}>Run cycle now</button>
          <button type="button" className="ghost" disabled={!!busy} onClick={refresh}>Refresh</button>
        </div>
        {intraday && (
          <p className="subtle" style={{ marginTop: 8 }}>
            Intraday sim: {intraday.state} · {intraday.symbol || '—'} · market {intraday.market_open_ist ? 'open' : 'closed'}
          </p>
        )}
      </section>

      <section className="panel">
        <div className="panel-head">
          <div><p className="eyebrow">PHASE A</p><h3>Prediction scoreboard</h3></div>
          <button type="button" className="ghost" disabled={!!busy} onClick={syncScoreboard}>Sync</button>
        </div>
        {scoreboard?.summary && (
          <p>
            Hit rate: <b>{scoreboard.summary.hit_rate_pct ?? '—'}%</b> · {scoreboard.summary.total} closed calls
          </p>
        )}
        <ul className="reason-list compact">
          {(scoreboard?.records || []).slice(0, 8).map(r => (
            <li key={r.id}>
              {r.symbol} {r.return_pct}% · {r.accuracy?.label} · {r.source}
            </li>
          ))}
        </ul>
      </section>

      <section className="panel">
        <div className="panel-head">
          <div><p className="eyebrow">PHASE E</p><h3>Calibration weights</h3></div>
          <button type="button" className="ghost" disabled={!!busy} onClick={recalibrate}>Recalibrate</button>
        </div>
        {calibration?.weights && (
          <ul className="reason-list compact">
            {Object.entries(calibration.weights).map(([k, v]) => (
              <li key={k}>{k}: {(Number(v) * 100).toFixed(1)}%</li>
            ))}
          </ul>
        )}
        {(calibration?.adjustments || []).slice(0, 4).map((a, i) => (
          <p key={i} className="subtle">{a}</p>
        ))}
      </section>

      <section className="panel">
        <div className="panel-head">
          <div><p className="eyebrow">ALERTS</p><h3>Watchlist agent feed</h3></div>
        </div>
        <AppAlertList
          alerts={alerts.slice(0, 12)}
          emptyMessage="No alerts yet — enable autopilot and set a watchlist."
        />
      </section>
      {dialog}
    </div>
  )
}

export default AutopilotDesk

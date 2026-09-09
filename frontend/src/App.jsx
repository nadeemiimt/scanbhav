import { useEffect, useMemo, useRef, useState } from 'react'
import PersonalAdvisor from './PersonalAdvisor'
import ScreenTable from './ScreenTable'
import { TradePlan15dPanel } from './components/TradePlan15dPanel'
import { TradePlan7dPanel, tradePlan7dHint } from './components/TradePlan7dPanel'
import { DailyTriggersPanel, dailyTriggersHint } from './components/DailyTriggersPanel'
import {
  effectiveScreenPageContract,
  fetchScreenPage,
  fetchScreenProviders,
  loadScreenUiState,
  mergeScreenCounts,
} from './screenApi'
import { APP_NAME, APP_MARK, APP_TAGLINE, APP_TITLE } from './brand'
import { addBookmarks, removeBookmark } from './bookmarkStore'
import { ChartGuideBanner, ChartGuideToggle, ChartGuideTooltip, useChartGuide } from './ChartGuide'
import {
  BookmarkStockButton,
  BookmarksHeaderButton,
  BookmarksModal,
  useBookmarks,
} from './Bookmarks'
import {
  AskModal,
  CoachPage,
  CompareModal,
  CustomWatchlist,
  DeskToolsBar,
  JournalModal,
  PracticeModal,
  PreBuyChecklist,
  SectorHeatPanel,
  SizeModal,
  VerdictStrip,
  aggregateTimeframe,
  exportBrief,
} from './deskFeatures'
import {
  AlertsBell,
  BacktestPanel,
  BreadthStrip,
  EventCalendar,
  GuidedWizard,
  InteractiveShell,
  LearnModeToggle,
  LevelsDesk,
  PortfolioHeatCard,
  SipCalculator,
  TeachableMetric,
} from './interactiveDesk'
import {
  AccountSync,
  CorrelationMatrix,
  CurriculumPanel,
  EarningsCalendar,
  ExportCenter,
  IntradayLevelsPanel,
  LivePulse,
  MfDiscovery,
  NotifySettings,
  OptionsDesk,
  PriceLevelDrawer,
  RemainingModal,
  RemainingToolsBar,
  RichJournal,
  SectorRsPanel,
  StrategyLab,
} from './remainingDesk'
import { DeepDossierPanel, InvestorPanel, TaSnapshot } from './components/analysis/AnalysisPanels'
import { ExtendedFactorsPanel } from './components/analysis/ExtendedFactorsPanel'
import { AnalyzeLoadingPanel } from './components/analysis/AnalyzeLoadingPanel'
import { ConvictionUniversePanel } from './components/analysis/ConvictionUniversePanel'
import { PlatformLimitationsPanel } from './components/analysis/PlatformLimitations'
import { ChartSuite } from './components/charts/ChartSuite'
import { MarketsPage, MoversPanel } from './components/markets/MarketsPage'
import { PortfolioPage } from './components/portfolio/PortfolioPage'
import { BrokerAccountsPage } from './components/broker/BrokerAccountsPage'
import { LivePredictionTracker } from './components/predictions/LivePredictionTracker'
import { GenaiResearchPanel } from './components/research/GenaiResearchPanel'
import AutopilotDesk from './components/trading/AutopilotDesk'
import { LiveModeBadge } from './components/trading/LiveModeBadge'
import { AboutPage } from './pages/AboutPage'
import { MethodPage } from './pages/MethodPage'
import {
  apiDelete,
  apiGet,
  apiGetOptional,
  apiPost,
  apiPostStream,
} from './lib/apiClient'
import { number, money, pretty } from './utils/analysisFormatters'
import { SwingDeskPage } from './swingDesk'
import { floorChatDelayMs } from './utils/floorChat'
import { AuthHeaderButton } from './components/auth/LoginModal'
import { SettingsHeaderButton, SettingsModal } from './components/SettingsModal'
import { loadSettings, saveSettings } from './lib/siteSettings'
import RequireAuth, { useAuthGate } from './components/auth/RequireAuth'
import { PRIMARY_NAV, SECONDARY_TAB_IDS, visiblePrimaryNav, visibleHorizons } from './appNav'
import { loadInitialAppRoute, tabFromLocation, writeAppUrl } from './appRoutes'

const MORE_TOOL_TITLES = {
  options: 'Options pulse',
  earnings: 'Earnings calendar',
  intraday: 'Intraday levels',
  correlation: 'Portfolio risk matrix',
  'sector-rs': 'Sector relative strength',
  strategy: 'Strategy lab',
  journal: 'Rich journal',
  export: 'Export / Import (PDF · CSV)',
  mf: 'Mutual fund discovery',
  courses: 'Learning curriculum',
  sync: 'Account sync',
  notify: 'Webhook & Telegram notify',
}

const HORIZON_ORDER = ['1d', '1w', '1m', '3m', '6m', '9m', '1y', '2y', '3y', '5y']

function normalizePredictedStance(raw) {
  const s = String(raw || 'neutral').toLowerCase().trim()
  const gradeMap = {
    a: 'strong_favorable',
    b: 'favorable',
    c: 'neutral',
    d: 'cautious',
    f: 'unfavorable',
  }
  if (gradeMap[s]) return gradeMap[s]
  const cleaned = s.replace(/[^a-z0-9_]+/g, '_').replace(/^_|_$/g, '')
  if (cleaned.length >= 2) return cleaned.slice(0, 40)
  return 'neutral'
}

const FALLBACK_TICKER = [
  { s: 'NIFTY', v: '—', c: '…', up: true, live: false },
  { s: 'SENSEX', v: '—', c: '…', up: true, live: false },
]

export default function App() {
  const initialRoute = useMemo(() => loadInitialAppRoute(), [])
  const initialSettings = useMemo(() => loadSettings(), [])
  const { authenticated, gate } = useAuthGate()
  const [tab, setTab] = useState(initialRoute.tab)
  const [menuOpen, setMenuOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [symbol, setSymbol] = useState('RELIANCE.NSE')
  const [provider, setProvider] = useState(initialSettings.provider)
  const [forceRefresh, setForceRefresh] = useState(initialSettings.forceRefresh)
  const [suggestions, setSuggestions] = useState([])
  const [searching, setSearching] = useState(false)
  const [loading, setLoading] = useState(false)
  const [analyzingSymbol, setAnalyzingSymbol] = useState('')
  const [analysis, setAnalysis] = useState(null)
  const [error, setError] = useState('')
  const searchTimer = useRef(null)
  const searchSeq = useRef(0)
  const analyzeSeq = useRef(0)
  const floorQueueRef = useRef([])
  const floorDrainRef = useRef(false)
  const floorRunIdRef = useRef(0)

  const [horizon, setHorizon] = useState('1m')
  const [screenLoading, setScreenLoading] = useState(false)
  const [screenPhase, setScreenPhase] = useState(null)
  const [screenProgress, setScreenProgress] = useState(null)
  const [screenInterrupted, setScreenInterrupted] = useState(null)
  const [screenCanResume, setScreenCanResume] = useState(null)
  const screenPollActiveRef = useRef(false)
  const [screen, setScreen] = useState(null)
  const [screenStale, setScreenStale] = useState(false)
  const [screenPage, setScreenPage] = useState(null)
  const [screenPageLoading, setScreenPageLoading] = useState(false)
  const [screenUi, setScreenUi] = useState(() => initialRoute.screenUi || loadScreenUiState())
  const [screenProviders, setScreenProviders] = useState(null)
  const [universeStatus, setUniverseStatus] = useState(null)

  const screenCounts = useMemo(
    () => mergeScreenCounts(screen, screenPage),
    [screen, screenPage],
  )

  const screenPageContract = useMemo(
    () => effectiveScreenPageContract(screenPage, screen, screenUi),
    [screenPage, screen, screenUi],
  )

  const [portfolio, setPortfolio] = useState(null)
  const [buyOpen, setBuyOpen] = useState(false)
  const [buyStep, setBuyStep] = useState('form') // form | upi | paying | done
  const [buyChecklistOk, setBuyChecklistOk] = useState(false)
  const [beginnerMode, setBeginnerMode] = useState(initialSettings.beginnerMode)
  const [learnMode, setLearnMode] = useState(initialSettings.learnMode)
  const [siteSettings, setSiteSettings] = useState(initialSettings)
  const deskMode = siteSettings.deskMode || 'mis'
  const navItems = useMemo(() => visiblePrimaryNav(deskMode), [deskMode])
  const horizonIds = useMemo(() => visibleHorizons(deskMode), [deskMode])
  const [wizardOpen, setWizardOpen] = useState(() => !localStorage.getItem('scanBhavWizard'))
  const [deskTool, setDeskTool] = useState(null) // compare | ask | practice | size | journal
  const [comparePair, setComparePair] = useState({ left: '', right: '' })
  const [moreTool, setMoreTool] = useState(null)
  const [priceLevels, setPriceLevels] = useState([])
  const [sectorHeat, setSectorHeat] = useState(null)
  const [breadth, setBreadth] = useState(null)
  const [buyForm, setBuyForm] = useState({ quantity: 10, asset_type: 'stock', equity_oriented: true })
  const [upiId, setUpiId] = useState('yourname@upi')
  const [portfolioBusy, setPortfolioBusy] = useState(false)
  const [marketBoard, setMarketBoard] = useState(null)
  const [marketsDesk, setMarketsDesk] = useState(null)
  const [tickerItems, setTickerItems] = useState(FALLBACK_TICKER)
  const [genaiProviders, setGenaiProviders] = useState(null)
  const [genaiProvider, setGenaiProvider] = useState('ollama')
  const [genaiModel, setGenaiModel] = useState('llama3.2:3b')
  const [genaiBusy, setGenaiBusy] = useState(false)
  const [genaiResult, setGenaiResult] = useState(null)
  const [genaiMessages, setGenaiMessages] = useState([])
  const [genaiRoster, setGenaiRoster] = useState([])
  const [genaiProgress, setGenaiProgress] = useState(0)
  const [genaiFloorTab, setGenaiFloorTab] = useState('floor')
  const [briefcaseOpen, setBriefcaseOpen] = useState(false)
  const [activeSpeaker, setActiveSpeaker] = useState(null)
  const [genaiModalOpen, setGenaiModalOpen] = useState(false)
  const [genaiExecuteTrades, setGenaiExecuteTrades] = useState(false)
  const [genaiTradeQty, setGenaiTradeQty] = useState(1)
  const [genaiAutonomousPicks, setGenaiAutonomousPicks] = useState(false)
  const [genaiMaxPicks, setGenaiMaxPicks] = useState(1)
  const [predictionTrack, setPredictionTrack] = useState(null)
  const [predictionBusy, setPredictionBusy] = useState(false)
  const [predictionLabOpen, setPredictionLabOpen] = useState(false)
  const [predictionNotice, setPredictionNotice] = useState('')
  const [bookmarksOpen, setBookmarksOpen] = useState(false)
  const { bookmarks, refresh: refreshBookmarks, setBookmarks } = useBookmarks()

  const quote = analysis?.quote
  const company = quote?.company ?? {}
  const tech = analysis?.technicals
  const ratings = analysis?.ratings
  const guide = analysis?.indicator_guide || {}
  const investors = analysis?.investors || []
  const candleData = useMemo(() => tech?.charts?.candles || [], [tech])
  const chartData = useMemo(
    () => (quote?.rows ?? [])
      .map(row => ({ date: row.date, close: Number(row['5. adjusted close'] || row['4. close']) }))
      .filter(row => Number.isFinite(row.close)),
    [quote],
  )

  const alertCount = useMemo(() => {
    const alerts = portfolio?.alerts || []
    return alerts.filter(a => a.level === 'sell' || a.level === 'buy_more').length
  }, [portfolio])

  const corrSymbols = useMemo(() => {
    const peers = ['RELIANCE.NSE', 'TCS.NSE', 'HDFCBANK.NSE', 'INFY.NSE', 'ICICIBANK.NSE']
    const fromHoldings = (portfolio?.holdings || []).map(h => h.symbol).filter(Boolean)
    const merged = [...fromHoldings, analysis?.symbol, symbol, ...peers].filter(Boolean)
    return [...new Set(merged)].slice(0, 8)
  }, [portfolio, analysis?.symbol, symbol])

  useEffect(() => {
    document.title = APP_TITLE
  }, [])

  useEffect(() => {
    setPriceLevels([])
  }, [analysis?.symbol])

  useEffect(() => {
    fetchScreenProviders().then(data => { if (data?.providers) setScreenProviders(data) }).catch(() => {})
    apiGetOptional('/api/ta/screen/last').then(data => {
      if (data) {
        setScreenStale(!!data.stale)
        setScreen(data)
        if (data.sector_heat) setSectorHeat(data.sector_heat)
      }
    }).catch(() => {})
    loadPortfolio()
    loadMarketBoard()
    loadMarketsDesk()
    loadPredictionTrack()
    apiGetOptional('/api/desk/sector-heat').then(data => {
      if (data) {
        setSectorHeat(data)
        if (data.breadth) setBreadth(data.breadth)
      }
    }).catch(() => {})
    apiGetOptional('/api/desk/breadth').then(data => {
      if (data) setBreadth(data)
    }).catch(() => {})
    apiGetOptional('/api/genai/providers').then(data => {
      if (!data) return
      setGenaiProviders(data)
      if (data.default_provider) setGenaiProvider(data.default_provider)
      if (data.default_model) setGenaiModel(data.default_model)
    }).catch(() => {})
    const timer = setInterval(loadMarketBoard, 5 * 60 * 1000)
    return () => {
      if (searchTimer.current) clearTimeout(searchTimer.current)
      clearInterval(timer)
    }
  }, [])

  useEffect(() => {
    // Normalize URL on first load (e.g. legacy /?scr_page=2 → /multi?scr_page=2).
    writeAppUrl(tab, tab === 'multi' ? screenUi : null, { replace: true })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onPopState = () => {
      const nextTab = tabFromLocation()
      setTab(nextTab)
      if (nextTab === 'multi') {
        setScreenUi(loadScreenUiState())
      }
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  useEffect(() => {
    if (tab !== 'multi') {
      setScreenPageLoading(false)
      return undefined
    }
    let cancelled = false
    const delay = screenUi.symbolFilter?.trim() ? 350 : 0
    setScreenPageLoading(true)
    const timer = setTimeout(() => {
      fetchScreenPage(screenUi)
        .then(data => {
          if (cancelled) return
          setScreenPage(data)
        })
        .catch(err => {
          if (!cancelled && err?.status !== 404) setError(err.message)
        })
        .finally(() => {
          if (!cancelled) setScreenPageLoading(false)
        })
    }, delay)
    return () => {
      cancelled = true
      clearTimeout(timer)
      setScreenPageLoading(false)
    }
  }, [tab, screenUi])

  useEffect(() => {
    if (tab !== 'multi' || screenPage?.rows?.length || screenPageLoading || !screen?.scored) return undefined
    let cancelled = false
    fetchScreenPage(screenUi)
      .then(data => { if (!cancelled) setScreenPage(data) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [tab, screen, screenPage, screenPageLoading, screenUi])

  useEffect(() => {
    if (tab !== 'multi') return
    apiGetOptional('/api/ta/universe/status')
      .then(data => { if (data?.refresh) setUniverseStatus(prev => prev || data.refresh) })
      .catch(() => {})
  }, [tab])

  useEffect(() => {
    if (tab !== 'multi') return undefined
    const controller = new AbortController()

    function applyStatus(st) {
      if (!st || controller.signal.aborted) return
      setScreenCanResume(st.can_resume ? (st.checkpoint || true) : null)
      if (st.phase === 'interrupted' && !st.running) {
        setScreenInterrupted(st)
      } else if (!st.running) {
        setScreenInterrupted(null)
      }
    }

    apiGetOptional('/api/ta/screen/status')
      .then(st => {
        applyStatus(st)
        if (controller.signal.aborted || !st?.running) return
        if (st.phase) setScreenPhase(st.phase)
        if (st.progress) setScreenProgress(st.progress)
        return pollScreenJobUntilDone({ fromStart: false, signal: controller.signal })
      })
      .catch(err => {
        if (!controller.signal.aborted) setError(err.message)
      })
    return () => controller.abort()
  }, [tab])

  useEffect(() => {
    const next = saveSettings({
      ...loadSettings(),
      beginnerMode,
      learnMode,
      provider,
      forceRefresh,
    })
    setSiteSettings(next)
  }, [beginnerMode, learnMode, provider, forceRefresh])

  useEffect(() => {
    if (!predictionLabOpen) return undefined
    const open = (predictionTrack?.items || []).filter(i => i.status === 'open')
    if (!open.length) return undefined
    const tick = async () => {
      try {
        const result = await apiPost('/api/predictions/track/refresh', { provider })
        setPredictionTrack(result)
      } catch {
        /* background refresh */
      }
    }
    const id = window.setInterval(tick, 90000)
    return () => window.clearInterval(id)
  }, [predictionLabOpen, predictionTrack?.items?.length, provider])

  function onSettingsSaved(next) {
    setSiteSettings(next)
    setBeginnerMode(next.beginnerMode)
    setLearnMode(next.learnMode)
    setProvider(next.provider)
    setForceRefresh(next.forceRefresh)
  }

  useEffect(() => {
    setBuyChecklistOk(false)
  }, [analysis?.symbol, buyOpen])

  function openDeskTool(id) {
    if (id === 'export') {
      if (!analysis) {
        setError('Analyze a stock first to export a brief.')
        return
      }
      exportBrief(analysis, genaiResult)
      return
    }
    if (id === 'journal' && !gate()) return
    setDeskTool(id)
  }

  function openCompareSymbols(symbols) {
    const pair = (symbols || []).map(s => String(s || '').trim().toUpperCase()).filter(Boolean)
    if (pair.length < 2) {
      setError('Select at least two symbols to compare.')
      return
    }
    setComparePair({ left: pair[0], right: pair[1] })
    setDeskTool('compare')
  }

  function bookmarkScreenRows(rows) {
    const { added } = addBookmarks((rows || []).map(row => ({
      symbol: row.symbol,
      name: row.symbol,
      lastPrice: row.price,
      changePct: row.horizon_return_pct,
      stance: row.stance,
      asOf: row.as_of,
    })))
    refreshBookmarks()
    if (added > 0) setError('')
  }

  const USER_MORE_TOOLS = new Set(['journal', 'sync', 'notify', 'correlation'])

  function openMoreTool(id) {
    if (USER_MORE_TOOLS.has(id) && !gate()) return
    setMoreTool(id)
  }

  async function loadPredictionTrack() {
    try {
      const data = await apiGetOptional('/api/predictions/track')
      if (data) {
        setPredictionTrack(data)
        if ((data.items || []).some(i => i.status === 'open')) {
          setPredictionLabOpen(true)
          try {
            const refreshed = await apiPost('/api/predictions/track/refresh', { provider })
            setPredictionTrack(refreshed)
          } catch {
            /* keep stored snapshot */
          }
        }
      }
    } catch {
      /* ignore */
    }
  }

  async function trackCurrentPrediction() {
    if (!analysis) {
      setError('Analyze a stock first, then track the prediction.')
      return
    }
    const entry = Number(company.live_price ?? tech?.price ?? quote?.summary?.close)
    if (!Number.isFinite(entry) || entry <= 0) {
      setError('No valid price to track. Re-run Analyze first.')
      return
    }
    setPredictionBusy(true)
    setError('')
    try {
      const rawStance = ratings?.composite_stance || analysis?.dossier?.conviction?.band || 'neutral'
      const predicted_stance = normalizePredictedStance(rawStance)
      const result = await apiPost('/api/predictions/track', {
        symbol: analysis.symbol,
        name: company.name || analysis.symbol,
        entry_price: entry,
        as_of: tech?.as_of || '',
        predicted_stance,
        predicted_horizon: ratings?.best_horizon || '1m',
        composite_score: ratings?.composite_score ?? null,
        conviction_score: analysis?.dossier?.conviction?.conviction_score ?? null,
        summary: analysis?.dossier?.conviction?.plain_english || '',
      })
      setPredictionTrack(result.track)
      setPredictionLabOpen(true)
      try {
        const refreshed = await apiPost('/api/predictions/track/refresh', { provider })
        setPredictionTrack(refreshed)
      } catch {
        /* keep pinned snapshot */
      }
      setPredictionNotice(`${analysis.symbol} pinned — live P&L updates after Refresh prices.`)
      window.setTimeout(() => setPredictionNotice(''), 5000)
      requestAnimationFrame(() => {
        document.getElementById('live-prediction-lab')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      })
    } catch (err) {
      setError(err.message || 'Track prediction failed')
    } finally {
      setPredictionBusy(false)
    }
  }

  async function refreshPredictions() {
    setPredictionBusy(true)
    setError('')
    try {
      const result = await apiPost('/api/predictions/track/refresh', { provider })
      setPredictionTrack(result)
      const n = result?.refreshed ?? 0
      if (n > 0) {
        setPredictionNotice(`Updated ${n} pinned price${n === 1 ? '' : 's'} from live/EOD feed.`)
        window.setTimeout(() => setPredictionNotice(''), 4000)
      } else {
        setError('Could not fetch newer prices — check backend is running and try again.')
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setPredictionBusy(false)
    }
  }

  async function ratePrediction(id, rating, notes = '') {
    setPredictionBusy(true)
    setError('')
    try {
      await apiPost(`/api/predictions/track/${encodeURIComponent(id)}/rate`, { rating, notes })
      await loadPredictionTrack()
    } catch (err) {
      setError(err.message)
    } finally {
      setPredictionBusy(false)
    }
  }

  async function removePrediction(id) {
    setPredictionBusy(true)
    setError('')
    try {
      await apiDelete(`/api/predictions/track/${encodeURIComponent(id)}`)
      await loadPredictionTrack()
    } catch (err) {
      setError(err.message)
    } finally {
      setPredictionBusy(false)
    }
  }

  async function loadMarketBoard() {
    try {
      const data = await apiGetOptional('/api/market/board?limit=500&top_n=10')
      if (!data) return
      setMarketBoard(data)
      if (data.ticker?.length) setTickerItems(data.ticker)
    } catch {
      /* keep fallback */
    }
  }

  async function loadMarketsDesk() {
    try {
      const data = await apiGetOptional('/api/markets/desk?limit=500&top_n=10')
      if (data) setMarketsDesk(data)
    } catch {
      /* ignore */
    }
  }

  async function loadPortfolio() {
    try {
      const data = await apiGetOptional('/api/portfolio')
      if (data) setPortfolio(data)
    } catch {
      /* ignore */
    }
  }

  function go(id) {
    setTab(id)
    setError('')
    setMenuOpen(false)
    window.scrollTo({ top: 0, behavior: 'smooth' })
    writeAppUrl(id, id === 'multi' ? screenUi : null, { replace: false })
    if (id === 'portfolio') loadPortfolio()
  }

  function search(value) {
    setSymbol(value)
    if (searchTimer.current) clearTimeout(searchTimer.current)
    if (value.trim().length < 2) {
      setSuggestions([])
      setSearching(false)
      return
    }
    setSearching(true)
    const seq = ++searchSeq.current
    searchTimer.current = setTimeout(async () => {
      try {
        const result = await apiGet(`/api/search?q=${encodeURIComponent(value.trim())}`)
        if (seq !== searchSeq.current) return
        setSuggestions(result.results ?? [])
      } catch (err) {
        if (seq !== searchSeq.current) return
        setSuggestions([])
        setError(err.message)
      } finally {
        if (seq === searchSeq.current) setSearching(false)
      }
    }, 120)
  }

  function looksLikeTicker(value) {
    const typed = value.trim().toUpperCase()
    return /^[A-Z0-9][A-Z0-9._-]{0,24}$/.test(typed) && (typed.includes('.') || !/\s/.test(value.trim()))
  }

  async function analyzeStock(selected = symbol) {
    let target = (selected || '').trim()
    if (!target) return
    if (!looksLikeTicker(target) && suggestions.length > 0) {
      target = (suggestions.find(item => item.name !== 'Use typed symbol') || suggestions[0]).symbol
    }
    if (!looksLikeTicker(target)) {
      setError('Pick a symbol from suggestions (e.g. RELIANCE.NSE).')
      return
    }
    setSymbol(target)
    setSuggestions([])
    const seq = ++analyzeSeq.current
    setAnalysis(null)
    setGenaiResult(null)
    setGenaiMessages([])
    setGenaiProgress(0)
    setGenaiFloorTab('floor')
    setBriefcaseOpen(false)
    setAnalyzingSymbol(target)
    setLoading(true)
    setError('')
    setTab('single')
    writeAppUrl('single', null, { replace: false })
    try {
      const result = await apiPost('/api/ta/analyze', { symbol: target, provider, force_refresh: forceRefresh })
      if (seq !== analyzeSeq.current) return
      setAnalysis(result)
      setGenaiResult(null)
      setGenaiMessages([])
      setGenaiProgress(0)
      setGenaiFloorTab('floor')
      setBriefcaseOpen(false)
      apiGetOptional(`/api/genai/history/${encodeURIComponent(target)}`)
        .then(hist => {
          if (seq !== analyzeSeq.current) return
          if (hist?.has_insight) {
            setGenaiResult(hist)
            setBriefcaseOpen(true)
          }
        })
        .catch(() => {})
    } catch (err) {
      if (seq !== analyzeSeq.current) return
      setError(err.message)
      setAnalysis(null)
    } finally {
      if (seq === analyzeSeq.current) setLoading(false)
    }
  }

  async function drainFloorChatQueue(runId) {
    if (floorDrainRef.current) return
    floorDrainRef.current = true
    try {
      while (floorQueueRef.current.length && floorRunIdRef.current === runId) {
        const item = floorQueueRef.current.shift()
        if (!item) break
        if (item.agent?.id) setActiveSpeaker(item.agent.id)
        setGenaiMessages(prev => [...prev, item])
        if (item.type === 'briefcase' && item._briefcaseResult) {
          setGenaiResult(item._briefcaseResult)
          setBriefcaseOpen(true)
          const switchRun = runId
          setTimeout(() => {
            if (floorRunIdRef.current === switchRun) setGenaiFloorTab('briefcase')
          }, Math.max(900, Math.min(2200, floorChatDelayMs(item.text, item.type) * 0.45)))
        }
        const delay = floorChatDelayMs(item.text, item.type)
        await new Promise(resolve => setTimeout(resolve, delay))
      }
    } finally {
      floorDrainRef.current = false
      if (floorQueueRef.current.length && floorRunIdRef.current === runId) {
        void drainFloorChatQueue(runId)
      }
    }
  }

  function enqueueFloorChat(msg, runId) {
    floorQueueRef.current.push(msg)
    drainFloorChatQueue(runId)
  }

  async function runGenaiResearch() {
    if (!analysis?.symbol) return
    const runId = floorRunIdRef.current + 1
    floorRunIdRef.current = runId
    floorQueueRef.current = []
    floorDrainRef.current = false

    setGenaiBusy(true)
    setError('')
    setGenaiMessages([])
    setGenaiProgress(0)
    setGenaiFloorTab('floor')
    setBriefcaseOpen(false)
    setActiveSpeaker(null)
    try {
      const response = await apiPostStream('/api/genai/research/stream', {
          symbol: analysis.symbol,
          provider: genaiProvider,
          model: genaiModel,
          market_provider: provider,
          force_refresh: false,
          execute_trades: genaiExecuteTrades,
          trade_quantity: genaiTradeQty,
          autonomous_picks: genaiAutonomousPicks,
          max_autonomous_picks: genaiMaxPicks,
        })
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        if (floorRunIdRef.current !== runId) break
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const chunks = buffer.split('\n\n')
        buffer = chunks.pop() || ''
        for (const chunk of chunks) {
          const line = chunk.split('\n').find(l => l.startsWith('data: '))
          if (!line) continue
          let event
          try {
            event = JSON.parse(line.slice(6))
          } catch {
            continue
          }
          if (event.progress != null) setGenaiProgress(event.progress)
          if (event.type === 'roster' && event.payload?.agents) {
            setGenaiRoster(event.payload.agents)
            continue
          }
          if (event.type === 'error' && event.text) {
            setGenaiResult(prev => ({
              ...(prev || {}),
              runError: event.text || 'Agent loop error',
              insight: prev?.insight || null,
              history: prev?.history || [],
            }))
            setError(event.text || 'Agent loop error')
          }
          if (['say', 'handoff', 'status', 'error', 'briefcase', 'done'].includes(event.type) && event.text) {
            const receivedAt = new Date().toISOString()
            const msg = {
              id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
              type: event.type,
              text: event.text,
              agent: event.agent,
              toAgent: event.to_agent,
              speakingTo: event.speaking_to,
              ts: event.ts || receivedAt,
              receivedAt,
            }
            if (event.type === 'briefcase' && event.payload?.result) {
              msg._briefcaseResult = event.payload.result
            }
            enqueueFloorChat(msg, runId)
          }
        }
      }
      // Wait until paced chat queue finishes for this run
      while (
        floorRunIdRef.current === runId
        && (floorQueueRef.current.length > 0 || floorDrainRef.current)
      ) {
        await new Promise(resolve => setTimeout(resolve, 120))
      }
    } catch (err) {
      setError(err.message)
      enqueueFloorChat({
        id: `err-${Date.now()}`,
        type: 'error',
        text: err.message,
        agent: { id: 'lead', name: 'Arjun Mehta', role: 'Desk Lead', initials: 'AM', accent: '#e8b84a' },
        ts: new Date().toISOString(),
        receivedAt: new Date().toISOString(),
      }, runId)
      while (
        floorRunIdRef.current === runId
        && (floorQueueRef.current.length > 0 || floorDrainRef.current)
      ) {
        await new Promise(resolve => setTimeout(resolve, 120))
      }
    } finally {
      if (floorRunIdRef.current === runId) {
        setGenaiBusy(false)
        setActiveSpeaker(null)
      }
    }
  }

  async function refreshScreenResults() {
    const [data, page] = await Promise.all([
      apiGetOptional('/api/ta/screen/last'),
      fetchScreenPage(screenUi).catch(() => null),
    ])
    if (data) {
      setScreenStale(!!data.stale)
      setScreen(data)
      if (data.sector_heat) setSectorHeat(data.sector_heat)
    }
    if (page) setScreenPage(page)
  }

  async function pollScreenJobUntilDone({ fromStart = false, signal } = {}) {
    if (screenPollActiveRef.current) return
    screenPollActiveRef.current = true
    setScreenLoading(true)
    let sawRunning = false
    try {
      for (let i = 0; i < 600; i += 1) {
        if (signal?.aborted) return
        if (i > 0) await new Promise(r => setTimeout(r, 1500))
        if (signal?.aborted) return
        const st = await apiGetOptional('/api/ta/screen/status')
        if (!st) continue
        if (st.phase) setScreenPhase(st.phase)
        if (st.running) sawRunning = true
        if (st.progress) setScreenProgress(st.progress)
        if (st.phase === 'error' || (st.phase === 'interrupted' && sawRunning)) {
          throw new Error(st.error || 'Screen failed')
        }
        if (st.phase === 'interrupted' && !sawRunning && !fromStart) break
        if (st.phase === 'done' || (sawRunning && !st.running)) break
        if (!sawRunning && fromStart && i >= 5 && st.phase === 'idle') {
          throw new Error('Screen did not start — API may be busy. Wait and try again.')
        }
        if (!sawRunning && !fromStart && st.phase === 'idle') break
      }
      await refreshScreenResults()
    } finally {
      screenPollActiveRef.current = false
      if (!signal?.aborted) {
        setScreenLoading(false)
        setScreenPhase(null)
        setScreenProgress(null)
      }
    }
  }

  async function runScreen(mode = 'fresh') {
    setScreenProgress(null)
    setScreenPhase('starting')
    setScreenInterrupted(null)
    setError('')
    setScreenStale(false)
    setScreenCanResume(null)
    const body = {
      limit: 500,
      horizon,
      force_refresh: forceRefresh,
      max_workers: 8,
      batch_size: 50,
      batch_pause_seconds: 1,
      retry_rounds: 1,
      retry_pause_seconds: 20,
      batch_strategy: 'round_robin',
      bucket: null,
      provider,
    }
    const kickUrl = `/api/ta/screen?background=true&mode=${mode}`
    try {
      const kick = await apiPost(kickUrl, body, { timeoutMs: 8000 }).catch(err => {
        if (String(err?.message || '').includes('timed out')) return null
        throw err
      })
      if (kick?.accepted === false) {
        throw new Error(kick.message || 'Could not start screen')
      }
      await pollScreenJobUntilDone({ fromStart: true })
      const st = await apiGetOptional('/api/ta/screen/status')
      if (st?.can_resume) setScreenCanResume(st.checkpoint)
      if (kick?.scored != null) {
        setScreen(kick)
        if (kick.sector_heat) setSectorHeat(kick.sector_heat)
        await refreshScreenResults()
      }
    } catch (err) {
      setError(err.message)
      setScreenLoading(false)
      setScreenPhase(null)
      setScreenProgress(null)
    }
  }

  async function purchaseCurrent() {
    if (!analysis) return
    if (!gate()) return
    setPortfolioBusy(true)
    setError('')
    setBuyStep('paying')
    try {
      // Dummy UPI settlement pause
      await new Promise(resolve => setTimeout(resolve, 1400))
      const price = company.live_price ?? tech?.price ?? quote?.summary?.close
      const result = await apiPost('/api/portfolio/buy', {
        symbol: analysis.symbol,
        quantity: Number(buyForm.quantity),
        price: quote?.summary?.close,
        asset_type: buyForm.asset_type,
        equity_oriented: buyForm.equity_oriented,
        provider,
      })
      setPortfolio(result.portfolio)
      setBuyStep('done')
      await apiPost('/api/portfolio/alerts/refresh', {})
        .then(data => { if (data?.portfolio) setPortfolio(data.portfolio) })
        .catch(() => {})
      setTimeout(() => {
        setBuyOpen(false)
        setBuyStep('form')
        go('portfolio')
      }, 900)
    } catch (err) {
      setError(err.message)
      setBuyStep('upi')
    } finally {
      setPortfolioBusy(false)
    }
  }

  const buyNotional = Number(buyForm.quantity || 0) * Number(company.live_price ?? tech?.price ?? quote?.summary?.close ?? 0)

  const price = company.live_price ?? tech?.price ?? quote?.summary?.close
  const change = company.live_price && company.previous_close
    ? ((company.live_price / company.previous_close) - 1) * 100
    : quote?.summary?.change_pct
  const positive = (change ?? 0) >= 0

  return (
    <div className="site">
      <div className="ticker-bar" aria-hidden="true">
        <div className="ticker-meta">
          {marketBoard?.meta?.indices_live
            ? <span className="ticker-status is-live">LIVE indices</span>
            : <span className="ticker-status is-loading">Index quotes loading…</span>}
          <span className="ticker-note">Stock movers = last cached session</span>
        </div>
        <div className="ticker-track-wrap">
          <div className="ticker-track">
            {[...tickerItems, ...tickerItems].map((item, i) => (
              <span className="ticker-item" key={`${item.s}-${i}`}>
                <b>{item.s}</b> {item.v} <span className={item.up ? 'up' : 'down'}>{item.c}</span>
              </span>
            ))}
          </div>
        </div>
      </div>

      <header className="site-header">
        <div className="header-inner">
          <button className="brand" onClick={() => go('single')} aria-label={`${APP_NAME} home`}>
            <span className="brand-mark">{APP_MARK}</span>
            <span className="brand-text">
              <span className="brand-name">{APP_NAME}</span>
              <span className="brand-tag">{APP_TAGLINE}</span>
            </span>
          </button>

          <nav className={`nav-links ${menuOpen ? 'open' : ''}`} aria-label="Primary">
            {navItems.map(item => (
              <button key={item.id} className={tab === item.id ? 'nav-link active' : 'nav-link'} onClick={() => go(item.id)}>
                {item.label}
                {item.id === 'portfolio' && alertCount > 0 && <span className="nav-badge">{alertCount}</span>}
              </button>
            ))}
          </nav>

          <div className="header-desk-actions">
            <LiveModeBadge />
            <AuthHeaderButton />
            <BookmarksHeaderButton
              count={bookmarks.length}
              active={bookmarksOpen}
              onClick={() => gate(() => setBookmarksOpen(true))}
            />
            <AlertsBell
              provider={provider}
              onAnalyze={(sym) => { setSymbol(sym); analyzeStock(sym); go('single') }}
            />
            <SettingsHeaderButton
              active={settingsOpen || SECONDARY_TAB_IDS.has(tab)}
              onClick={() => setSettingsOpen(true)}
            />
          </div>

          <button className="menu-toggle" onClick={() => setMenuOpen(v => !v)} aria-label="Menu">☰</button>
        </div>
      </header>

      <div className="site-main">
        {tab === 'single' && (
          <section className="page-hero">
            <div>
              <p className="eyebrow">India equities · neural research desk</p>
              <h1>Read the tape.<br /><span>Rank the horizon.</span></h1>
              <p>
                Full technical stack with hover explainers, candle charts, investor-style lenses,
                and a local paper portfolio with Zerodha/Groww fees plus Indian STCG/LTCG tax.
              </p>
            </div>
            <div className="hero-stats">
              <article className="hero-stat"><p>Horizons</p><strong>10</strong></article>
              <article className="hero-stat"><p>Indicators</p><strong>30+</strong></article>
              <article className="hero-stat"><p>Investors</p><strong>5</strong></article>
            </div>
          </section>
        )}

        {(tab === 'single' || tab === 'multi') && (
          <nav className="tabs" aria-label="Workspace">
            <button className={tab === 'single' ? 'tab active' : 'tab'} onClick={() => go('single')}>Single Stock</button>
            <button className={tab === 'multi' ? 'tab active' : 'tab'} onClick={() => go('multi')}>Multi Screen (Nifty 500)</button>
          </nav>
        )}

        {(tab === 'single' || tab === 'multi') && (
          <section className="search-card">
            <div className="search-row">
              {tab === 'single' ? (
                <div className="search-box">
                  <input
                    value={symbol}
                    onChange={e => search(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && analyzeStock()}
                    placeholder="Search name or code, e.g. Adani or RELIANCE.NSE"
                    autoComplete="off"
                  />
                  {searching && <p className="search-hint">Searching…</p>}
                  {suggestions.length > 0 && (
                    <div className="suggestions" role="listbox">
                      {suggestions.map(item => (
                        <button key={`${item.symbol}-${item.exchange}`} type="button" onMouseDown={e => e.preventDefault()} onClick={() => analyzeStock(item.symbol)}>
                          <b>{item.symbol}</b>
                          <span>{item.name} {item.exchange && `· ${item.exchange}`}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <>
                  <label>
                    Rank horizon
                    <select value={horizon} onChange={e => setHorizon(e.target.value)}>
                      {HORIZON_ORDER.map(id => <option key={id} value={id}>{id.toUpperCase()}</option>)}
                    </select>
                  </label>
                </>
              )}
              <select value={provider} onChange={e => setProvider(e.target.value)}>
                {(screenProviders?.providers || [
                  { id: 'auto', label: 'Auto (Yahoo → NSE)' },
                  { id: 'yfinance', label: 'Yahoo Finance' },
                  { id: 'nse', label: 'NSE public data' },
                ]).map(p => (
                  <option key={p.id} value={p.id}>{p.label}</option>
                ))}
              </select>
              <label className="refresh-toggle">
                <input type="checkbox" checked={forceRefresh} onChange={e => setForceRefresh(e.target.checked)} />
                Refresh
              </label>
              {tab === 'single' ? (
                <button className={`primary${loading ? ' is-loading' : ''}`} onClick={() => analyzeStock()} disabled={loading}>
                  {loading ? 'Scanning…' : 'Analyze'}
                </button>
              ) : (
                <>
                  <button className="primary" onClick={() => runScreen('fresh')} disabled={screenLoading}>
                    {screenLoading ? 'Screening…' : 'Run screen'}
                  </button>
                  {screenCanResume && !screenLoading && (
                    <>
                      <button type="button" className="ghost" onClick={() => runScreen('resume')}>
                        Resume ({screenCanResume.scored ?? '?'}/{screenCanResume.universe_size ?? 500})
                      </button>
                      <button type="button" className="ghost" onClick={() => runScreen('restart')}>
                        Restart
                      </button>
                    </>
                  )}
                </>
              )}
            </div>
            {tab === 'single' && analysis && !loading && (
              <LivePulse
                symbol={analysis.symbol}
                onRefresh={() => analyzeStock(analysis.symbol)}
                autoRefresh={false}
                refreshOnLtp={false}
              />
            )}
            <p>
              {tab === 'single'
                ? 'Deep technical scorecard, candle charts, and famous-investor pattern lenses.'
                : 'Score official Nifty 500 (Large / Mid / Small) with the full technical engine and rank by horizon.'}
            </p>
          </section>
        )}

        {error && <section className="error">{error}</section>}

        {tab === 'single' && loading && (
          <AnalyzeLoadingPanel symbol={analyzingSymbol || symbol} />
        )}

        {tab === 'single' && !analysis && !loading && (
          <section className="empty">Search a stock and click Analyze to unlock 1D → 5Y technical ratings.</section>
        )}

        {tab === 'single' && analysis && !loading && (
          <>
            <section className="hero">
              <div>
                <div className="hero-title-row">
                  <p className="eyebrow">{company.name || analysis.symbol}</p>
                  <BookmarkStockButton
                    symbol={analysis.symbol}
                    name={company.name || analysis.symbol}
                    lastPrice={price}
                    changePct={change}
                    stance={ratings?.composite_stance}
                    asOf={tech?.as_of}
                    onChange={setBookmarks}
                    requireAuth={!authenticated}
                    onAuthRequired={() => gate()}
                  />
                </div>
                <h2>{number.format(price)}</h2>
                <p className={positive ? 'up' : 'down'}>{positive ? '▲' : '▼'} {number.format(Math.abs(change ?? 0))}% · as of {tech?.as_of}</p>
                {predictionNotice && (
                  <p className="subtle pred-track-notice">{predictionNotice}</p>
                )}
                <div className="hero-actions">
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => go('swing')}
                  >
                    Swing desk
                  </button>
                  <button
                    type="button"
                    className="primary genai-launch"
                    onClick={(e) => {
                      e.preventDefault()
                      e.stopPropagation()
                      setGenaiFloorTab('floor')
                      setGenaiModalOpen(true)
                    }}
                  >
                    Gen AI live desk
                  </button>
                  <button
                    type="button"
                    className="ghost"
                    disabled={predictionBusy}
                    onClick={(e) => {
                      e.preventDefault()
                      e.stopPropagation()
                      trackCurrentPrediction()
                    }}
                  >
                    {predictionBusy ? 'Tracking…' : 'Track prediction'}
                  </button>
                  <button
                    type="button"
                    className="ghost"
                    onClick={(e) => {
                      e.preventDefault()
                      e.stopPropagation()
                      gate(() => {
                        setBuyForm(f => ({ ...f, quantity: 10, asset_type: 'stock' }))
                        setBuyStep('form')
                        setBuyOpen(true)
                      })
                    }}
                  >
                    Purchase
                  </button>
                  <button
                    type="button"
                    className="ghost"
                    onClick={(e) => {
                      e.preventDefault()
                      e.stopPropagation()
                      go('portfolio')
                    }}
                  >
                    Open portfolio
                  </button>
                </div>
              </div>
              <div className="composite">
                <p className="eyebrow">COMPOSITE</p>
                <h2 className={`grade grade-${ratings?.composite_grade || 'C'}`}>{ratings?.composite_score ?? '—'}</h2>
                <p>{ratings?.composite_grade || '—'} · {pretty(ratings?.composite_stance || 'mixed')}</p>
                {analysis?.relative_strength?.headline && (
                  <p className="subtle rs-line">{analysis.relative_strength.headline.plain}</p>
                )}
              </div>
            </section>

            <VerdictStrip analysis={analysis} beginnerMode={beginnerMode} />

            {/* Priority sequence: dossier → collapsed plans → charts → investor lenses */}
            {!beginnerMode && analysis.dossier && (
              <DeepDossierPanel dossier={analysis.dossier} />
            )}
            {beginnerMode && analysis.dossier && (
              <section className="panel beginner-focus">
                <div className="panel-head">
                  <div>
                    <p className="eyebrow">BEGINNER FOCUS</p>
                    <h3>What matters for this name</h3>
                  </div>
                </div>
                <p>{analysis.dossier?.conviction?.plain_english || 'Run Analyze for a plain-English read.'}</p>
                <ul className="reason-list compact">
                  {(analysis.dossier?.signal_radar?.green_flags || []).slice(0, 3).map((f, i) => (
                    <li key={`g${i}`}>{typeof f === 'string' ? f : f.text || f.title}</li>
                  ))}
                  {(analysis.dossier?.signal_radar?.red_flags || []).slice(0, 2).map((f, i) => (
                    <li key={`r${i}`} className="down">{typeof f === 'string' ? f : f.text || f.title}</li>
                  ))}
                </ul>
                <p className="subtle">Turn off Beginner mode in Desk tools to see the full dossier, investor lenses, and TA board.</p>
              </section>
            )}

            {analysis && deskMode === 'full' && (
              <div className="desk-plans-stack">
                {analysis?.plan_15d?.ok && (
                  <InteractiveShell
                    eyebrow="15-DAY PLAN"
                    title="Entry & exit levels"
                    defaultOpen={false}
                    hint={analysis.plan_15d.plain?.slice(0, 100) || 'Pullback entry, exit target, and stop'}
                  >
                    <TradePlan15dPanel plan={analysis.plan_15d} embedded />
                  </InteractiveShell>
                )}
                {analysis?.plan_7d?.ok && (
                  <InteractiveShell
                    eyebrow="7-DAY SWING MAP"
                    title="Pullback & recovery scenarios"
                    defaultOpen={false}
                    hint={tradePlan7dHint(analysis.plan_7d)}
                  >
                    <TradePlan7dPanel plan={analysis.plan_7d} embedded includeTriggers={false} />
                  </InteractiveShell>
                )}
                {analysis?.plan_7d?.triggers?.length > 0 && (
                  <InteractiveShell
                    eyebrow="TRIGGERS"
                    title="Daily triggers"
                    defaultOpen={false}
                    hint={dailyTriggersHint(analysis.plan_7d.triggers)}
                  >
                    <DailyTriggersPanel triggers={analysis.plan_7d.triggers} />
                  </InteractiveShell>
                )}
                <InteractiveShell
                  eyebrow="RESEARCH LIMITS"
                  title="What this desk is — and is not"
                  defaultOpen={false}
                  hint="Research desk — not a broker or live terminal"
                >
                  <PlatformLimitationsPanel
                    embedded
                    dataAsOf={tech?.as_of}
                    cached={quote?.metadata?.cached}
                  />
                </InteractiveShell>
              </div>
            )}

            {!beginnerMode && analysis.extended && (
              <ExtendedFactorsPanel extended={analysis.extended} ratings={ratings} />
            )}

            <ChartSuite
              candleData={candleData}
              chartData={chartData}
              levels={tech?.levels}
              session={analysis.session_levels}
              priceLevels={priceLevels}
              guide={guide}
              extended={analysis.extended}
            />

            {!beginnerMode && deskMode === 'full' && <InvestorPanel investors={investors} />}

            {/* Later / collapsed by default */}
            <InteractiveShell
              eyebrow="DESK"
              title="Desk tools"
              defaultOpen={false}
              hint="Compare, Ask, Options, Export, Learn / Beginner"
            >
              <DeskToolsBar
                symbol={analysis.symbol}
                beginnerMode={beginnerMode}
                onToggleBeginner={(checked) => setBeginnerMode(Boolean(checked))}
                onOpen={openDeskTool}
                extra={(
                  <LearnModeToggle learnMode={learnMode} onToggle={setLearnMode} />
                )}
              />
              <RemainingToolsBar onOpen={openMoreTool} />
            </InteractiveShell>

            <InteractiveShell
              eyebrow="HORIZONS"
              title={deskMode === 'mis' ? 'Intraday horizons (1D · 1W)' : '1 Day → 5 Years ratings'}
              defaultOpen={false}
              hint="Composite scores across holding periods"
            >
              <div className="horizon-grid">
                {horizonIds.map(id => {
                  const item = ratings.horizons[id]
                  if (!item) return null
                  return (
                    <article key={id} className={`horizon-card stance-${item.stance}`}>
                      <p className="eyebrow">{id.toUpperCase()}</p>
                      <h3>{item.score}</h3>
                      <p className={`grade grade-${item.grade}`}>{item.grade} · {pretty(item.stance)}</p>
                      <p className="subtle">Return: {item.horizon_return_pct != null ? `${number.format(item.horizon_return_pct)}%` : '—'}</p>
                    </article>
                  )
                })}
              </div>
              {!beginnerMode && ratings.best_horizon && (
                <div style={{ marginTop: 14 }}>
                  <p className="eyebrow">WHY ({(ratings.best_horizon || '').toUpperCase()})</p>
                  <ul className="reason-list">
                    {(ratings.horizons[ratings.best_horizon]?.reasons || []).map((reason, i) => <li key={i}>{reason}</li>)}
                  </ul>
                </div>
              )}
            </InteractiveShell>

            {!beginnerMode && (
              <InteractiveShell
                eyebrow="TECHNICALS"
                title="Indicator board"
                defaultOpen={false}
                hint="RSI, MACD, MAs, volume, levels"
              >
                <TaSnapshot tech={tech} guide={guide} learnMode={learnMode} />
              </InteractiveShell>
            )}

            <InteractiveShell
              eyebrow="SESSION"
              title="Levels & volume"
              defaultOpen={false}
              hint="Prior day, gap, pivot, volume profile"
            >
              <LevelsDesk levels={tech?.levels} session={analysis.session_levels} />
              {!analysis.session_levels?.available && (
                <p className="subtle">Session levels unavailable for this symbol right now.</p>
              )}
            </InteractiveShell>

            <InteractiveShell
              eyebrow="CALENDAR"
              title="Events & headlines"
              defaultOpen={false}
              hint="Risk flags, earnings, news catalysts"
            >
              <EventCalendar events={analysis.event_watch} news={analysis.news} />
            </InteractiveShell>

            <InteractiveShell
              eyebrow="PREDICTIONS"
              title="Live prediction lab"
              defaultOpen={false}
              open={predictionLabOpen}
              onOpenChange={setPredictionLabOpen}
              hint="Track thesis vs price over time"
            >
              <LivePredictionTracker
                track={predictionTrack}
                busy={predictionBusy}
                onRefresh={refreshPredictions}
                onRate={ratePrediction}
                onRemove={removePrediction}
                onTrackHere={trackCurrentPrediction}
                canTrack={Boolean(analysis)}
                onAnalyze={sym => { setSymbol(sym); analyzeStock(sym) }}
              />
            </InteractiveShell>

            {!beginnerMode && (
              <InteractiveShell
                eyebrow="TOOLS"
                title="Levels draw · strategy backtest"
                defaultOpen={false}
                hint="Manual price levels and rule backtests"
              >
                <PriceLevelDrawer levels={priceLevels} setLevels={setPriceLevels} />
                <div style={{ marginTop: 14 }}>
                  <BacktestPanel symbol={analysis.symbol} provider={provider} onError={setError} />
                </div>
              </InteractiveShell>
            )}

            {!beginnerMode && marketBoard && (
              <InteractiveShell
                eyebrow="TAPE"
                title="Desk movers"
                defaultOpen={false}
                hint="Cached session winners and losers"
              >
                <MoversPanel
                  board={marketBoard}
                  onAnalyze={sym => { setSymbol(sym); analyzeStock(sym) }}
                  onRefresh={loadMarketBoard}
                />
              </InteractiveShell>
            )}

            {buyOpen && (
              <div className="genai-modal-backdrop buy-modal-backdrop" role="dialog" aria-modal="true" aria-label="Paper purchase">
                <div className="genai-modal buy-modal">
                  <section className="panel buy-panel in-modal">
                    <div className="panel-head">
                      <div>
                        <p className="eyebrow">PAPER BUY</p>
                        <h3>{buyStep === 'upi' || buyStep === 'paying' || buyStep === 'done' ? 'UPI payment' : `Add ${analysis.symbol}`}</h3>
                      </div>
                      <button type="button" className="ghost" onClick={() => { setBuyOpen(false); setBuyStep('form'); setBuyChecklistOk(false) }}>Close</button>
                    </div>

                    {buyStep === 'form' && (
                      <div className="buy-grid">
                        <PreBuyChecklist analysis={analysis} accepted={buyChecklistOk} setAccepted={setBuyChecklistOk} />
                        <label>
                          Asset type
                          <select value={buyForm.asset_type} onChange={e => setBuyForm(f => ({ ...f, asset_type: e.target.value }))}>
                            <option value="stock">Stock</option>
                            <option value="mutual_fund">Mutual fund</option>
                          </select>
                        </label>
                        <label>
                          Quantity / units
                          <input type="number" min="0.001" step="1" value={buyForm.quantity} onChange={e => setBuyForm(f => ({ ...f, quantity: e.target.value }))} />
                        </label>
                        {buyForm.asset_type === 'mutual_fund' && (
                          <label className="refresh-toggle">
                            <input type="checkbox" checked={buyForm.equity_oriented} onChange={e => setBuyForm(f => ({ ...f, equity_oriented: e.target.checked }))} />
                            Equity-oriented MF (STCG/LTCG). Uncheck for debt MF (slab tax).
                          </label>
                        )}
                        <p className="subtle">Amount: {money.format(buyNotional || 0)} at ₹{number.format(price)} · Dummy UPI next — no real money moves.</p>
                        <button
                          type="button"
                          className="primary"
                          disabled={!buyChecklistOk || !buyForm.quantity || Number(buyForm.quantity) <= 0}
                          onClick={() => setBuyStep('upi')}
                        >
                          Confirm purchase → UPI
                        </button>
                      </div>
                    )}

                    {(buyStep === 'upi' || buyStep === 'paying' || buyStep === 'done') && (
                      <UpiPaymentScreen
                        symbol={analysis.symbol}
                        amount={buyNotional}
                        quantity={buyForm.quantity}
                        price={price}
                        upiId={upiId}
                        setUpiId={setUpiId}
                        step={buyStep}
                        busy={portfolioBusy}
                        onBack={() => setBuyStep('form')}
                        onPay={purchaseCurrent}
                      />
                    )}
                  </section>
                </div>
              </div>
            )}

            <CompareModal
              open={deskTool === 'compare'}
              onClose={() => setDeskTool(null)}
              leftSymbol={comparePair.left || analysis?.symbol}
              rightSymbol={comparePair.right}
              provider={provider}
              onError={setError}
              onAnalyze={sym => { setDeskTool(null); setSymbol(sym); analyzeStock(sym) }}
            />
            <AskModal
              open={deskTool === 'ask'}
              onClose={() => setDeskTool(null)}
              symbol={analysis.symbol}
              provider={provider}
              onError={setError}
            />
            <PracticeModal
              open={deskTool === 'practice'}
              onClose={() => setDeskTool(null)}
              symbol={analysis.symbol}
              provider={provider}
              onError={setError}
            />
            <SizeModal
              open={deskTool === 'size'}
              onClose={() => setDeskTool(null)}
              analysis={analysis}
              onError={setError}
              onApplyShares={(shares) => {
                gate(() => {
                  setBuyForm(f => ({ ...f, quantity: String(shares) }))
                  setDeskTool(null)
                  setBuyOpen(true)
                  setBuyStep('form')
                })
              }}
            />
            <JournalModal
              open={deskTool === 'journal'}
              onClose={() => setDeskTool(null)}
              symbol={analysis.symbol}
            />

            <RemainingModal
              open={Boolean(moreTool)}
              onClose={() => setMoreTool(null)}
              title={MORE_TOOL_TITLES[moreTool] || 'Desk tool'}
            >
              {moreTool === 'options' && (
                <OptionsDesk symbol={analysis.symbol} analysis={analysis} marketBoard={marketBoard} />
              )}
              {moreTool === 'earnings' && <EarningsCalendar symbol={analysis.symbol} />}
              {moreTool === 'intraday' && (
                <IntradayLevelsPanel symbol={analysis.symbol} provider={provider} />
              )}
              {moreTool === 'correlation' && (
                <RequireAuth title="Portfolio risk matrix" description="Sign in to analyze correlations across your holdings.">
                  <CorrelationMatrix symbols={corrSymbols} provider={provider} onError={setError} />
                </RequireAuth>
              )}
              {moreTool === 'sector-rs' && (
                <SectorRsPanel onAnalyze={(sym) => { setMoreTool(null); setSymbol(sym); analyzeStock(sym) }} />
              )}
              {moreTool === 'strategy' && (
                <StrategyLab symbol={analysis.symbol} provider={provider} onError={setError} />
              )}
              {moreTool === 'journal' && (
                <RequireAuth title="Trading journal" description="Sign in to save and sync your journal entries.">
                  <RichJournal symbol={analysis.symbol} />
                </RequireAuth>
              )}
              {moreTool === 'export' && (
                <ExportCenter
                  analysis={analysis}
                  genaiResult={genaiResult}
                  holdings={portfolio?.holdings || []}
                />
              )}
              {moreTool === 'mf' && <MfDiscovery onError={setError} />}
              {moreTool === 'courses' && <CurriculumPanel />}
              {moreTool === 'sync' && (
                <RequireAuth title="Account sync" description="Sign in to link broker accounts and sync holdings.">
                  <AccountSync />
                </RequireAuth>
              )}
              {moreTool === 'notify' && (
                <RequireAuth title="Alert settings" description="Sign in to manage portfolio alerts tied to your account.">
                  <NotifySettings alerts={portfolio?.alerts || []} />
                </RequireAuth>
              )}
            </RemainingModal>

            {genaiModalOpen && (
              <div className="genai-modal-backdrop" role="dialog" aria-modal="true" aria-label="Live Research Desk">
                <div className="genai-modal research-desk-modal">
                  <GenaiResearchPanel
                    symbol={analysis.symbol}
                    providers={genaiProviders}
                    provider={genaiProvider}
                    setProvider={setGenaiProvider}
                    model={genaiModel}
                    setModel={setGenaiModel}
                    busy={genaiBusy}
                    result={genaiResult}
                    onRun={runGenaiResearch}
                    messages={genaiMessages}
                    roster={genaiRoster}
                    progress={genaiProgress}
                    floorTab={genaiFloorTab}
                    setFloorTab={setGenaiFloorTab}
                    briefcaseOpen={briefcaseOpen}
                    activeSpeaker={activeSpeaker}
                    executeTrades={genaiExecuteTrades}
                    setExecuteTrades={setGenaiExecuteTrades}
                    tradeQuantity={genaiTradeQty}
                    setTradeQuantity={setGenaiTradeQty}
                    autonomousPicks={genaiAutonomousPicks}
                    setAutonomousPicks={setGenaiAutonomousPicks}
                    maxAutonomousPicks={genaiMaxPicks}
                    setMaxAutonomousPicks={setGenaiMaxPicks}
                    modal
                    onClose={() => setGenaiModalOpen(false)}
                  />
                </div>
              </div>
            )}

            <p className="subtle">{ratings.disclaimer}</p>
            <p className="subtle">Indicators: {(analysis.indicators_used || []).join(' · ')}</p>
          </>
        )}

        {tab === 'multi' && (
          <section className="panel">
            <div className="panel-head">
              <div>
                <p className="eyebrow">NIFTY 500 SCREEN</p>
                <h3>Ranked by {horizon.toUpperCase()} technical score</h3>
              </div>
              <span>
                {screenLoading
                  ? (screenProgress
                    ? `${screenPhase === 'warming_cache' ? 'Warming cache' : 'Scanning'} ${screenProgress.scored_so_far ?? 0}/${screenProgress.total ?? 500}${screenProgress.failed_so_far ? ` · ${screenProgress.failed_so_far} failed` : ''}`
                    : 'Scan in progress…')
                  : screenCounts.scanned > 0 || screenCounts.universe
                    ? `${screenCounts.scanned}/${screenCounts.universe} scanned`
                    : screen
                      ? `${screen.scored}/${screen.universe_size} scored · ${screen.elapsed_seconds}s`
                      : 'Not run yet'}
              </span>
            </div>

            {universeStatus?.as_of && (
              <p className="subtle">
                Universe checked {universeStatus.as_of}
                {universeStatus.refreshed ? ' · refreshed from NSE today' : ' · using saved list'}
              </p>
            )}

            {(screenInterrupted || screenCanResume) && !screenLoading && (
              <div className="error screen-stale-banner">
                {screenCanResume ? (
                  <>
                    Partial scan saved: {screenCanResume.scored ?? screenInterrupted?.progress?.scored_so_far ?? '?'}
                    /{screenCanResume.universe_size ?? 500} scored.
                    {' '}Use <b>Resume</b> to continue or <b>Restart</b> from scratch.
                  </>
                ) : (
                  <>
                    Scan stopped at {screenInterrupted?.progress?.scored_so_far ?? '?'}/
                    {screenInterrupted?.progress?.total ?? 500} (no checkpoint — progress was lost).
                    {' '}
                    <button type="button" className="linkish" onClick={() => runScreen('restart')}>Restart scan</button>
                  </>
                )}
              </div>
            )}

            {screenStale && !screen && !screenInterrupted && !screenCanResume && (
              <div className="error screen-stale-banner">
                Previous run only scored ~200 stocks. Click <b>Run screen</b> for the full Nifty 500 (Large / Mid / Small). First run may take several minutes while prices cache.
              </div>
            )}

            {screenLoading && (
              <div className="screen-running-banner">
                <p className="subtle">
                  <strong>Scan running</strong>
                  {' — '}
                {screenPhase === 'warming_cache'
                    ? 'Warming price cache (Yahoo batches) — scoring starts in ~1–2 min…'
                    : screenProgress && (screenProgress.scored_so_far ?? 0) === 0
                      ? 'Scoring started — first symbols take ~30s each…'
                      : screenProgress
                        ? `Scoring ${screenProgress.scored_so_far ?? 0}/${screenProgress.total ?? 500} · failed ${screenProgress.failed_so_far ?? 0}`
                        : 'Starting…'}
                  {' · '}
                  Full Nifty 500 may take 15–25 min. Do not reload API during scan.
                </p>
              </div>
            )}

            {screen?.sections && (
              <div className="cap-section-summary cap-section-compact paper-rank">
                {['large', 'mid', 'small'].map(key => {
                  const sec = screen.sections[key]
                  if (!sec) return null
                  const leader = (sec.top || [])[0]
                  const capTotal = screenCounts[key] ?? sec.total ?? '—'
                  const capScanned = screenCounts[`${key}_scanned`] ?? sec.scored ?? 0
                  return (
                    <article key={key} className="gain">
                      <p className="eyebrow">{sec.label}</p>
                      <h3>{capScanned}<span className="cap-total">/{capTotal}</span></h3>
                      <p>{leader ? `#1 ${leader.symbol.replace('.NSE', '')} · ${number.format(leader.score)}` : '—'}</p>
                    </article>
                  )
                })}
              </div>
            )}

            <ConvictionUniversePanel
              onAnalyze={sym => { setSymbol(sym); analyzeStock(sym); go('single') }}
              onRowClick={sym => { setSymbol(sym); analyzeStock(sym); go('single') }}
            />

            {(screenPageContract || screen) ? (
              <ScreenTable
                pageContract={screenPageContract}
                ui={screenUi}
                onUiChange={setScreenUi}
                loading={screenPageLoading}
                onRowClick={(sym) => { setSymbol(sym); analyzeStock(sym) }}
                onCompareSymbols={openCompareSymbols}
                onBookmarkSymbols={bookmarkScreenRows}
              />
            ) : screenPageLoading ? (
              <p className="subtle">Loading screener table…</p>
            ) : null}

            {!screen && !screenPageContract && !screenPageLoading && (
              <p className="subtle">No cached screen yet — click Run screen, or wait if the backend is starting.</p>
            )}

            {screen && (
              <>
                {screen.failed > 0 && <p className="subtle">{screen.failed} symbols failed (insufficient history or fetch errors).</p>}
                <p className="subtle">{screen.disclaimer}</p>
                {screen.meta?.source && <p className="subtle">Universe: {screen.meta.source} · as of {screen.meta.as_of || '—'}</p>}
                {(screen.data_provider || screenPage?.run?.data_provider) && (
                  <p className="subtle">
                    Price data: {(screenProviders?.providers || []).find(p => p.id === (screen.data_provider || screenPage?.run?.data_provider))?.label
                      || screen.data_provider
                      || screenPage?.run?.data_provider}
                  </p>
                )}
              </>
            )}
          </section>
        )}

        {tab === 'portfolio' && (
          <RequireAuth
            title="Portfolio dashboard"
            description="Sign in to track paper trades, alerts, and tax-aware P&L across sessions."
          >
            <PortfolioPage
              portfolio={portfolio}
              setPortfolio={setPortfolio}
              setError={setError}
              onAnalyze={sym => { setSymbol(sym); analyzeStock(sym) }}
            />
          </RequireAuth>
        )}

        {tab === 'accounts' && (
          <RequireAuth
            title="Broker accounts"
            description="Sign in to view live Zerodha/Groww/FYERS holdings and sell-all."
          >
            <BrokerAccountsPage onError={setError} />
          </RequireAuth>
        )}

        {tab === 'swing' && (
          <SwingDeskPage
            symbol={symbol}
            setSymbol={setSymbol}
            provider={provider}
            screenProviders={screenProviders}
            setHorizon={setHorizon}
            onError={setError}
            onAnalyze={sym => { setSymbol(sym); analyzeStock(sym); go('single') }}
            onCompare={sym => { setSymbol(sym); openDeskTool('compare') }}
            onOpenJournal={() => openDeskTool('journal')}
            onOpenBacktest={() => go('interactive')}
            onPortfolioBuy={async trade => {
              if (!gate()) return
              setError('')
              try {
                const result = await apiPost('/api/portfolio/buy', {
                  symbol: trade.symbol,
                  quantity: trade.shares,
                  price: trade.entry,
                  asset_type: 'equity',
                  provider,
                })
                setPortfolio(result.portfolio)
                go('portfolio')
              } catch (err) {
                setError(err.message)
              }
            }}
            go={go}
            seedAnalysis={analysis?.symbol === symbol ? analysis : null}
          />
        )}

        {tab === 'autopilot' && (
          <AutopilotDesk />
        )}

        {tab === 'coach' && (
          <div className="coach-stack">
            <CoachPage
              provider={provider}
              onError={setError}
              symbol={symbol}
              onAnalyze={sym => { setSymbol(sym); analyzeStock(sym); go('single') }}
              advisorSlot={(
                <RequireAuth
                  title="Personal Advisor"
                  description="Sign in to save email profiles, ingest portfolios, and receive exit-review alerts."
                >
                  <PersonalAdvisor provider={provider} onError={setError} />
                </RequireAuth>
              )}
            />
            <div className="coach-extras">
              <InteractiveShell eyebrow="COACH" title="SIP calculator" defaultOpen={false} hint="Long-term SIP projection">
                <SipCalculator onError={setError} />
              </InteractiveShell>
              <InteractiveShell eyebrow="COACH" title="Strategy lab" defaultOpen={false} hint="Backtest sweep">
                <StrategyLab symbol={symbol} provider={provider} onError={setError} />
              </InteractiveShell>
              <InteractiveShell eyebrow="COACH" title="MF discovery" defaultOpen={false}>
                <MfDiscovery onError={setError} />
              </InteractiveShell>
              <InteractiveShell eyebrow="COACH" title="Learning curriculum" defaultOpen={false}>
                <CurriculumPanel />
              </InteractiveShell>
              <InteractiveShell eyebrow="COACH" title="Account sync" defaultOpen={false}>
                <RequireAuth title="Account sync" description="Sign in to link broker accounts and sync holdings.">
                  <AccountSync />
                </RequireAuth>
              </InteractiveShell>
            </div>
          </div>
        )}
        {tab === 'markets' && (
          <MarketsPage
            board={marketBoard}
            marketsDesk={marketsDesk}
            heat={sectorHeat || screen?.sector_heat}
            breadth={breadth || marketsDesk?.breadth}
            onRefresh={() => { loadMarketBoard(); loadMarketsDesk() }}
            onAnalyze={sym => { setSymbol(sym); analyzeStock(sym) }}
            go={go}
          />
        )}
        {tab === 'method' && <MethodPage go={go} />}
        {tab === 'about' && <AboutPage go={go} onGuide={() => setWizardOpen(true)} />}
      </div>

      <BookmarksModal
        open={bookmarksOpen && authenticated}
        onClose={() => setBookmarksOpen(false)}
        bookmarks={bookmarks}
        onAnalyze={(sym) => {
          setBookmarksOpen(false)
          setSymbol(sym)
          analyzeStock(sym)
          go('single')
        }}
        onRemove={(sym) => {
          setBookmarks(removeBookmark(sym))
          refreshBookmarks()
        }}
      />

      <GuidedWizard
        open={wizardOpen}
        onClose={() => setWizardOpen(false)}
        onEnableBeginner={() => setBeginnerMode(true)}
        onAnalyze={(sym) => { setSymbol(sym); analyzeStock(sym); go('single') }}
      />

      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        settings={siteSettings}
        onChange={onSettingsSaved}
        screenProviders={screenProviders}
        currentTab={tab}
        onNavigate={id => go(id)}
        onRerunWizard={() => {
          localStorage.removeItem('scanBhavWizard')
          setWizardOpen(true)
        }}
      />

      <footer className="site-footer">
        <div className="footer-inner">
          <div className="footer-brand">
            <div className="brand-name">{APP_NAME}</div>
            <p>Local technical research desk for Indian equities and mutual funds — horizon ratings, portfolio paper trading, and transparent fees/tax math.</p>
          </div>
          <div className="footer-col">
            <h4>Workspace</h4>
            <button onClick={() => go('single')}>Single stock analysis</button>
            <button onClick={() => go('multi')}>Multi stock screener</button>
            <button onClick={() => go('swing')}>Swing desk</button>
            <button onClick={() => go('portfolio')}>Portfolio dashboard</button>
          </div>
          <div className="footer-col">
            <h4>Learn</h4>
            <button onClick={() => go('method')}>Indicators &amp; desk reference</button>
            <button onClick={() => go('about')}>About {APP_NAME}</button>
          </div>
          <div className="footer-col">
            <h4>Desk notes</h4>
            <button type="button">Educational use only</button>
            <button type="button">Not investment advice</button>
            <button type="button">Fees ≈ Zerodha / Groww</button>
          </div>
        </div>
        <div className="footer-bottom">
          <span>© {new Date().getFullYear()} {APP_NAME} · Built for local research</span>
          <span>Past performance and technical scores are not forecasts.</span>
        </div>
      </footer>
    </div>
  )
}


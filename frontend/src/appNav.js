/** Primary header nav vs secondary pages opened from Settings. */

export const MIS_DESK_NAV = [
  { id: 'autopilot', label: 'Autopilot' },
  { id: 'multi', label: 'Screener' },
  { id: 'single', label: 'Analyze' },
  { id: 'markets', label: 'Markets' },
  { id: 'accounts', label: 'Accounts' },
]

export const RESEARCH_NAV = [
  { id: 'swing', label: 'Swing' },
  { id: 'portfolio', label: 'Portfolio' },
]

/** Full nav — all features remain reachable (PDF + research stack preserved). */
export const PRIMARY_NAV = [
  { id: 'single', label: 'Analyze' },
  { id: 'multi', label: 'Screener' },
  { id: 'swing', label: 'Swing' },
  { id: 'autopilot', label: 'Autopilot' },
  { id: 'portfolio', label: 'Portfolio' },
  { id: 'accounts', label: 'Accounts' },
  { id: 'markets', label: 'Markets' },
]

export const SECONDARY_NAV = [
  { id: 'coach', label: 'Coach', hint: 'Practice & drills' },
  { id: 'method', label: 'Reference', hint: 'Indicators & desk guide' },
  { id: 'about', label: 'About', hint: 'Platform & limits' },
]

export const ALL_NAV = [...PRIMARY_NAV, ...SECONDARY_NAV]

export const SECONDARY_TAB_IDS = new Set(SECONDARY_NAV.map(item => item.id))

/** MIS desk mode: execution-first nav. Full mode: entire product surface. */
export function visiblePrimaryNav(deskMode = 'full') {
  if (deskMode === 'mis') {
    return MIS_DESK_NAV
  }
  return PRIMARY_NAV
}

export const MIS_HORIZONS = ['1d', '1w']

export const FULL_HORIZONS = ['1d', '1w', '1m', '3m', '6m', '9m', '1y', '2y', '3y', '5y']

export function visibleHorizons(deskMode = 'full') {
  return deskMode === 'mis' ? MIS_HORIZONS : FULL_HORIZONS
}

/** Research-only tabs hidden in MIS mode (still reachable via Settings → More desks). */
export const MIS_HIDDEN_TAB_IDS = new Set(['swing', 'portfolio', 'coach'])

export function isTabHiddenInMis(tabId, deskMode = 'full') {
  return deskMode === 'mis' && MIS_HIDDEN_TAB_IDS.has(tabId)
}

import { useRef, useState } from 'react'
import { apiGet } from '../lib/apiClient'
import { normalizeAppSymbol } from '../lib/symbolValidate'

export function looksLikeTicker(value) {
  const typed = (value || '').trim().toUpperCase()
  return /^[A-Z0-9][A-Z0-9._-]{0,24}$/.test(typed) && (typed.includes('.') || !/\s/.test((value || '').trim()))
}

function symbolRoot(symbol) {
  return (symbol || '').toUpperCase().replace(/\.(NSE|BSE|NS|BO)$/, '')
}

function toAppSymbol(symbol) {
  try {
    return normalizeAppSymbol(symbol)
  } catch {
    return null
  }
}

export function useSymbolSearch(initial = '') {
  const [query, setQuery] = useState(initial)
  const [suggestions, setSuggestions] = useState([])
  const [searching, setSearching] = useState(false)
  const searchTimer = useRef(null)
  const searchSeq = useRef(0)

  function onQueryChange(value) {
    setQuery(value)
    if (searchTimer.current) clearTimeout(searchTimer.current)
    const trimmed = value.trim()
    if (trimmed.length < 2) {
      setSuggestions([])
      setSearching(false)
      return
    }
    setSearching(true)
    const seq = ++searchSeq.current
    searchTimer.current = setTimeout(async () => {
      try {
        const result = await apiGet(`/api/search?q=${encodeURIComponent(trimmed)}`)
        if (seq !== searchSeq.current) return
        setSuggestions(result.results ?? [])
      } catch {
        if (seq !== searchSeq.current) return
        setSuggestions([])
      } finally {
        if (seq === searchSeq.current) setSearching(false)
      }
    }, 120)
  }

  function clearSuggestions() {
    setSuggestions([])
  }

  async function resolveSymbol(input = query) {
    const target = (input || '').trim()
    if (!target) return null

    const upper = target.toUpperCase()
    const root = symbolRoot(upper)

    if (suggestions.length > 0) {
      const exact = suggestions.find(item => item.symbol.toUpperCase() === upper)
      if (exact) return toAppSymbol(exact.symbol)
      const byRoot = suggestions.find(
        item => item.name !== 'Use typed symbol' && symbolRoot(item.symbol) === root,
      )
      if (byRoot) return toAppSymbol(byRoot.symbol)
    }

    if (looksLikeTicker(target)) {
      const withExchange = toAppSymbol(upper)
      if (withExchange) return withExchange
      try {
        const result = await apiGet(`/api/search?q=${encodeURIComponent(target)}`)
        const list = result.results ?? []
        const match = list.find(item => symbolRoot(item.symbol) === root)
        if (match) return toAppSymbol(match.symbol)
      } catch {
        /* fall through */
      }
      return null
    }

    try {
      const result = await apiGet(`/api/search?q=${encodeURIComponent(target)}`)
      const list = result.results ?? []
      if (list.length) {
        const pick = list.find(item => item.name !== 'Use typed symbol') || list[0]
        return toAppSymbol(pick.symbol)
      }
    } catch {
      /* fall through */
    }
    return null
  }

  return {
    query,
    setQuery,
    suggestions,
    setSuggestions,
    searching,
    onQueryChange,
    clearSuggestions,
    resolveSymbol,
  }
}

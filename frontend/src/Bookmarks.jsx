import { useCallback, useEffect, useState } from 'react'
import {
  isBookmarked as checkBookmarked,
  loadBookmarks,
  removeBookmark,
  toggleBookmark,
  upsertBookmarkMeta,
} from './bookmarkStore'

function BookmarkSvg({ filled = false, className = '' }) {
  return (
    <svg
      className={`bookmark-icon ${filled ? 'filled' : ''} ${className}`.trim()}
      viewBox="0 0 24 24"
      width="18"
      height="18"
      aria-hidden
    >
      <path
        d="M6 4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16l-6-3.5L6 20V4z"
        fill={filled ? 'currentColor' : 'none'}
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function useBookmarks() {
  const [bookmarks, setBookmarks] = useState(() => loadBookmarks())

  const refresh = useCallback(() => setBookmarks(loadBookmarks()), [])

  useEffect(() => {
    function onStorage(e) {
      if (e.key === 'scanBhavBookmarks') refresh()
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [refresh])

  return { bookmarks, refresh, setBookmarks }
}

export function BookmarkStockButton({
  symbol,
  name,
  lastPrice,
  changePct,
  stance,
  asOf,
  className = '',
  onChange,
  requireAuth = false,
  onAuthRequired,
}) {
  const [saved, setSaved] = useState(() => checkBookmarked(symbol))

  useEffect(() => {
    setSaved(checkBookmarked(symbol))
  }, [symbol])

  useEffect(() => {
    if (!symbol || !saved) return
    const list = upsertBookmarkMeta(symbol, {
      name: name || symbol,
      lastPrice,
      changePct,
      stance,
      asOf,
    })
    onChange?.(list)
  }, [symbol, name, lastPrice, changePct, stance, asOf, saved, onChange])

  function handleToggle() {
    if (requireAuth) {
      onAuthRequired?.()
      return
    }
    const { bookmarked, list } = toggleBookmark({
      symbol,
      name: name || symbol,
      lastPrice,
      changePct,
      stance,
      asOf,
    })
    setSaved(bookmarked)
    onChange?.(list)
  }

  if (!symbol) return null

  return (
    <button
      type="button"
      className={`bookmark-toggle ${saved ? 'saved' : ''} ${className}`.trim()}
      onClick={handleToggle}
      aria-pressed={saved}
      title={saved ? 'Remove bookmark' : 'Bookmark this stock'}
    >
      <BookmarkSvg filled={saved} />
      <span>{saved ? 'Bookmarked' : 'Bookmark'}</span>
    </button>
  )
}

export function BookmarksHeaderButton({ count, onClick, active }) {
  return (
    <button
      type="button"
      className={`ghost bookmarks-header-btn ${active ? 'active' : ''}`}
      onClick={onClick}
      aria-label={`Bookmarks${count ? `, ${count} saved` : ''}`}
      title="View bookmarked stocks"
    >
      <BookmarkSvg filled={count > 0} />
      {count > 0 && <span className="bookmarks-count">{count}</span>}
    </button>
  )
}

function formatWhen(iso) {
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

export function BookmarksModal({ open, onClose, bookmarks, onAnalyze, onRemove }) {
  useEffect(() => {
    if (!open) return undefined
    function onKey(e) {
      if (e.key === 'Escape') onClose?.()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      className="genai-modal-backdrop bookmarks-modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label="Bookmarked stocks"
      onClick={e => { if (e.target === e.currentTarget) onClose?.() }}
    >
      <div className="bookmarks-modal panel">
        <div className="panel-head">
          <div>
            <p className="eyebrow">SAVED STOCKS</p>
            <h3>Bookmarks</h3>
          </div>
          <button type="button" className="ghost" onClick={onClose}>Close</button>
        </div>

        <p className="subtle bookmarks-lede">
          Stocks you bookmarked on the single-stock desk — click a row to analyze.
        </p>

        {!bookmarks.length && (
          <div className="bookmarks-empty">
            <BookmarkSvg filled />
            <p>No bookmarks yet.</p>
            <p className="subtle">Analyze a stock and tap <strong>Bookmark</strong> on its header.</p>
          </div>
        )}

        {bookmarks.length > 0 && (
          <div className="table-wrap bookmarks-table-wrap">
            <table className="bookmarks-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Name</th>
                  <th>Last</th>
                  <th>Change</th>
                  <th>Saved</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {bookmarks.map(item => {
                  const ch = item.changePct
                  const chCls = ch == null ? '' : ch >= 0 ? 'up' : 'down'
                  return (
                    <tr key={item.symbol} className="bookmarks-row">
                      <td>
                        <button
                          type="button"
                          className="linkish bookmarks-open"
                          onClick={() => onAnalyze?.(item.symbol)}
                        >
                          {item.symbol}
                        </button>
                      </td>
                      <td>{item.name || '—'}</td>
                      <td>{item.lastPrice != null ? Number(item.lastPrice).toFixed(2) : '—'}</td>
                      <td className={chCls}>
                        {ch != null ? `${ch >= 0 ? '+' : ''}${Number(ch).toFixed(2)}%` : '—'}
                      </td>
                      <td className="subtle">{formatWhen(item.bookmarkedAt)}</td>
                      <td>
                        <button
                          type="button"
                          className="ghost bookmarks-remove"
                          aria-label={`Remove ${item.symbol}`}
                          onClick={() => onRemove?.(item.symbol)}
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

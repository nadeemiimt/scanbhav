import { number } from '../../utils/analysisFormatters'
import { CustomWatchlist, SectorHeatPanel } from '../../deskFeatures'
import { BreadthStrip } from '../../interactiveDesk'

export function MoversPanel({ board, onAnalyze, onRefresh }) {
  if (!board) return null
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">TRENDING TODAY</p>
          <h3>Top 10 winners & losers</h3>
        </div>
        <button type="button" className="ghost" onClick={onRefresh}>Refresh</button>
      </div>
      <p className="subtle" style={{ marginBottom: 12 }}>{board.meta?.note}</p>
      <div className="movers-grid">
        <div>
          <h4 className="up">Winners</h4>
          <MoversTable rows={board.winners || []} onAnalyze={onAnalyze} />
        </div>
        <div>
          <h4 className="down">Losers</h4>
          <MoversTable rows={board.losers || []} onAnalyze={onAnalyze} />
        </div>
      </div>
      {!(board.winners || []).length && (
        <p className="subtle">No cached prices yet — run the Multi Screen once to fill the universe cache, then refresh.</p>
      )}
    </section>
  )
}

function MoversTable({ rows, onAnalyze }) {
  if (!rows?.length) return <p className="subtle">No data</p>
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr><th>#</th><th>Symbol</th><th>Price</th><th>1D %</th></tr>
        </thead>
        <tbody>
          {rows.map(row => (
            <tr key={row.symbol} className="clickable" onClick={() => onAnalyze(row.symbol)}>
              <td>{row.rank}</td>
              <td>{row.symbol}</td>
              <td>{number.format(row.price)}</td>
              <td className={row.change_pct >= 0 ? 'up' : 'down'}>{row.change_pct >= 0 ? '+' : ''}{number.format(row.change_pct)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SectorBoardTable({ sectors }) {
  if (!sectors?.length) return <p className="subtle">Run screener once, then refresh markets desk.</p>
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr><th>Sector</th><th>1M %</th><th>3M %</th><th>RSI</th></tr>
        </thead>
        <tbody>
          {sectors.map(s => (
            <tr key={s.sector}>
              <td>{s.sector}</td>
              <td className={(s.return_1m_pct ?? 0) >= 0 ? 'up' : 'down'}>{number.format(s.return_1m_pct)}%</td>
              <td>{number.format(s.return_3m_pct)}%</td>
              <td>{number.format(s.rsi_14)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function FiiStrip({ fii }) {
  if (!fii || fii.status !== 'ok') {
    return <p className="subtle">FII/DII daily flows unavailable off-hours or when NSE rate-limits.</p>
  }
  return <p className="subtle">FII/DII feed connected ({fii.source}). See Analyze extended block for symbol-level holdings.</p>
}

export function MarketsPage({ board, marketsDesk, heat, breadth, onRefresh, onAnalyze, go }) {
  const picks = [
    { symbol: 'RELIANCE.NSE', name: 'Reliance Industries', blurb: 'Energy-to-retail bellwether' },
    { symbol: 'TCS.NSE', name: 'Tata Consultancy', blurb: 'IT services quality compounder' },
    { symbol: 'HDFCBANK.NSE', name: 'HDFC Bank', blurb: 'Private banking benchmark' },
    { symbol: 'INFY.NSE', name: 'Infosys', blurb: 'Digital services pulse check' },
    { symbol: 'ICICIBANK.NSE', name: 'ICICI Bank', blurb: 'Franchise + growth mix' },
    { symbol: 'SBIN.NSE', name: 'State Bank of India', blurb: 'PSU banking proxy' },
  ]
  const vix = marketsDesk?.vix || (board?.indices || []).find(i => /vix/i.test(`${i.id || ''} ${i.name || ''} ${i.label || ''}`))
  const regime = marketsDesk?.regime?.regime || {}
  const sectorBoard = marketsDesk?.sector_board?.sectors || []

  return (
    <section className="content-page">
      <p className="eyebrow">Markets</p>
      <h2>Desk watchlist & macro context</h2>
      <p>Indices from Yahoo. Breadth, sector board, regime, FII/DII from universe cache + NSE public feeds.</p>

      {board?.indices?.length > 0 && (
        <div className="hero-stats markets-indices">
          {board.indices.map(ix => (
            <article className="hero-stat" key={ix.id}>
              <p>{ix.id} {ix.live ? '· live' : ''}</p>
              <strong>{number.format(ix.price)}</strong>
              <span className={(ix.change_pct || 0) >= 0 ? 'up' : 'down'}>
                {ix.change_pct != null ? `${ix.change_pct >= 0 ? '+' : ''}${number.format(ix.change_pct)}%` : '—'}
              </span>
            </article>
          ))}
        </div>
      )}

      <BreadthStrip breadth={breadth || heat?.breadth} />

      {breadth?.new_52w_highs != null && (
        <section className="panel">
          <div className="panel-head">
            <div><p className="eyebrow">BREADTH</p><h3>New highs / lows</h3></div>
            <button type="button" className="ghost" onClick={onRefresh}>Refresh</button>
          </div>
          <p>{breadth.plain}</p>
        </section>
      )}

      <div className="markets-layout markets-desk-grid">
        <section className="panel">
          <div className="panel-head">
            <div><p className="eyebrow">REGIME</p><h3>{regime.regime || '—'} · {regime.regime_score ?? '—'}</h3></div>
          </div>
          <p className="subtle">
            VIX pctile {marketsDesk?.regime?.vix?.percentile_1y ?? '—'} ({marketsDesk?.regime?.vix?.label || 'n/a'}).
          </p>
          <FiiStrip fii={marketsDesk?.fii_dii} />
        </section>
        <section className="panel">
          <div className="panel-head">
            <div><p className="eyebrow">SECTOR BOARD</p><h3>Leader: {marketsDesk?.sector_board?.leader || '—'}</h3></div>
          </div>
          <SectorBoardTable sectors={sectorBoard} />
        </section>
      </div>

      <div className="markets-layout">
        <CustomWatchlist onAnalyze={(sym) => { onAnalyze(sym); go('single') }} />
        <SectorHeatPanel heat={heat} onAnalyze={(sym) => { onAnalyze(sym); go('single') }} />
      </div>

      {vix && (
        <section className="panel options-lite">
          <div className="panel-head">
            <div><p className="eyebrow">VOLATILITY</p><h3>India VIX</h3></div>
          </div>
          <p>
            VIX ≈ <strong>{number.format(vix.price ?? vix.value ?? 0)}</strong>
            {vix.change_pct != null && (
              <span className={(vix.change_pct ?? 0) >= 0 ? 'down' : 'up'}>
                {' '}{vix.change_pct >= 0 ? '+' : ''}{number.format(vix.change_pct)}%
              </span>
            )}
          </p>
        </section>
      )}

      <MoversPanel board={board} onAnalyze={(sym) => { onAnalyze(sym); go('single') }} onRefresh={onRefresh} />

      <section className="panel">
        <div className="panel-head"><div><p className="eyebrow">PRESET WATCH</p><h3>Large-cap starters</h3></div></div>
        <div className="watch-grid">
          {picks.map(p => (
            <article key={p.symbol}>
              <h4>{p.name}</h4>
              <p className="subtle">{p.blurb}</p>
              <button type="button" className="ghost" onClick={() => { onAnalyze(p.symbol); go('single') }}>Analyze {p.symbol}</button>
            </article>
          ))}
        </div>
      </section>
    </section>
  )
}

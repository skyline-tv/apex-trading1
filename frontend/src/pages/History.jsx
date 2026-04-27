import { useState, useEffect } from 'react'
import { RefreshCw, TrendingUp, TrendingDown, Minus, Search, Filter } from 'lucide-react'
import Card, { CardLabel } from '../components/Card'
import Spinner from '../components/Spinner'
import { getHistory, getPortfolio, getRuleLogs, API_BASE_URL } from '../api'

const BADGE = {
  BUY: { cls: 'text-accent  bg-accent/10  border-accent/25', Icon: TrendingUp },
  SELL: { cls: 'text-red     bg-red/10     border-red/25', Icon: TrendingDown },
  HOLD: { cls: 'text-yellow  bg-yellow/10  border-yellow/25', Icon: Minus },
}

function DecisionBadge({ decision }) {
  const { cls, Icon } = BADGE[decision] || BADGE.HOLD
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border font-mono text-[10px] font-bold ${cls}`}>
      <Icon size={10} />
      {decision}
    </span>
  )
}

function ActionLabel({ actionType }) {
  const labelMap = {
    close_long: 'Close Long',
    close_short: 'Close Short',
  }
  const label = labelMap[actionType] || actionType || '-'
  return <span className="font-mono text-[10px] text-blue">{label}</span>
}

function sideLabels(actionType) {
  if (actionType === 'close_short') {
    return { entry: 'SELL', exit: 'BUY' }
  }
  return { entry: 'BUY', exit: 'SELL' }
}

export default function History() {
  const [trades, setTrades] = useState([])
  const [ruleLogs, setRuleLogs] = useState([])
  const [portfolio, setPortfolio] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [limit, setLimit] = useState(50)
  const [assetFilter, setAssetFilter] = useState('')
  const [decisionFilter, setDecisionFilter] = useState('ALL')
  const [refreshing, setRefreshing] = useState(false)

  const fetch = async (options = {}) => {
    const { silent = false } = options
    if (silent) setRefreshing(true)
    else setLoading(true)
    setError('')
    try {
      const [hRes, pRes, lRes] = await Promise.allSettled([
        getHistory(limit, { closedOnly: true }),
        getPortfolio(),
        getRuleLogs(80),
      ])

      if (hRes.status !== 'fulfilled') {
        throw new Error('history fetch failed')
      }
      setTrades(hRes.value.data.trades || [])

      if (pRes.status === 'fulfilled') {
        setPortfolio(pRes.value.data || null)
      }
      if (lRes.status === 'fulfilled') {
        setRuleLogs(lRes.value.data?.logs || [])
      }
    } catch {
      const target = API_BASE_URL || 'VITE_API_URL not configured'
      setError(`Cannot reach backend at ${target}`)
    } finally {
      if (silent) setRefreshing(false)
      else setLoading(false)
    }
  }

  useEffect(() => {
    fetch()
  }, [limit])

  useEffect(() => {
    const id = setInterval(() => fetch({ silent: true }), 15000)
    return () => clearInterval(id)
  }, [limit])

  const fmt = (n) =>
    n != null
      ? `Rs ${Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      : '-'

  const formatDate = (ts) => {
    if (!ts) return '-'
    const d = new Date(ts)
    return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  }

  const filteredTrades = trades.filter((t) => {
    const matchAsset = !assetFilter || t.asset?.toUpperCase().includes(assetFilter.toUpperCase())
    const matchDecision = decisionFilter === 'ALL' || t.decision === decisionFilter
    return matchAsset && matchDecision
  })

  return (
    <div className="animate-fade-in space-y-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="font-sans font-800 text-2xl text-white tracking-tight">Closed Trades</h1>
          <p className="font-mono text-[11px] text-muted mt-0.5 tracking-widest">
            {filteredTrades.length}/{trades.length} CLOSED TRADES SHOWN
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative">
            <Search size={12} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <input
              type="text"
              placeholder="Filter asset..."
              value={assetFilter}
              onChange={(e) => setAssetFilter(e.target.value)}
              className="bg-surface border border-border text-white font-mono text-xs pl-7 pr-3 py-2 rounded-lg w-36 focus:outline-none focus:border-accent/50"
            />
          </div>
          <div className="relative">
            <Filter size={12} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <select
              value={decisionFilter}
              onChange={(e) => setDecisionFilter(e.target.value)}
              className="bg-surface border border-border text-white font-mono text-xs pl-7 pr-3 py-2 rounded-lg focus:outline-none focus:border-accent/50"
            >
              {['ALL', 'BUY', 'SELL'].map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
          </div>
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="bg-surface border border-border text-white font-mono text-xs px-3 py-2 rounded-lg focus:outline-none focus:border-accent/50"
          >
            {[25, 50, 100, 250].map((n) => (
              <option key={n} value={n}>Last {n}</option>
            ))}
          </select>
          <button
            onClick={() => fetch({ silent: true })}
            className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border text-muted hover:text-white hover:border-white/20 transition font-mono text-xs"
          >
            {loading || refreshing ? <Spinner size={13} /> : <RefreshCw size={13} />}
            Refresh
          </button>
        </div>
      </div>

      {error && <div className="border border-red/30 bg-red/5 rounded-xl px-4 py-3 font-mono text-xs text-red">{error}</div>}
      {refreshing && !loading && (
        <div className="border border-border bg-surface rounded-xl px-4 py-3 font-mono text-xs text-muted">
          Refreshing trades and rule logs...
        </div>
      )}

      {filteredTrades.length > 0 && (() => {
        const closeLongs = filteredTrades.filter((t) => t.action_type === 'close_long').length
        const closeShorts = filteredTrades.filter((t) => t.action_type === 'close_short').length
        const winners = filteredTrades.filter((t) => Number(t.profit || 0) > 0).length
        const realizedPnl = filteredTrades.reduce((s, t) => s + (t.profit || 0), 0)
        const livePnl = portfolio?.total_pnl ?? 0
        return (
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-3">
            {[
              { label: 'Closed Longs', value: closeLongs, color: 'text-red' },
              { label: 'Closed Shorts', value: closeShorts, color: 'text-accent' },
              { label: 'Winning Closes', value: winners, color: 'text-blue' },
              { label: 'Realized P&L', value: `${realizedPnl >= 0 ? '+' : ''}${fmt(realizedPnl)}`, color: realizedPnl >= 0 ? 'text-accent' : 'text-red' },
              { label: 'Live Total P&L', value: `${livePnl >= 0 ? '+' : ''}${fmt(livePnl)}`, color: livePnl >= 0 ? 'text-accent' : 'text-red' },
            ].map(({ label, value, color }) => (
              <Card key={label}>
                <CardLabel>{label}</CardLabel>
                <p className={`font-mono text-xl font-bold ${color}`}>{value}</p>
              </Card>
            ))}
          </div>
        )
      })()}

      <Card>
        {loading ? (
          <div className="flex justify-center py-16"><Spinner size={32} /></div>
        ) : trades.length === 0 ? (
          <div className="text-center py-16">
            <p className="font-mono text-sm text-muted">No closed trades yet.</p>
            <p className="font-mono text-xs text-muted/60 mt-1">Open positions will appear here after they are closed.</p>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="grid grid-cols-1 gap-3 md:hidden">
              {filteredTrades.map((t) => {
                const sides = sideLabels(t.action_type)
                return (
                  <div key={t.id} className="rounded-lg border border-border bg-bg px-4 py-3">
                    <div className="flex items-center justify-between gap-2">
                      <p className="font-mono text-xs text-accent font-bold">{t.asset}</p>
                      <DecisionBadge decision={t.decision} />
                    </div>
                    <p className="font-mono text-[10px] text-muted mt-1">{formatDate(t.timestamp)}</p>
                    <div className="mt-2">
                      <ActionLabel actionType={t.action_type} />
                    </div>
                    <div className="mt-2 grid grid-cols-2 gap-2 font-mono text-[11px]">
                      <p className="text-muted">Entry: <span className="text-white">{sides.entry}</span></p>
                      <p className="text-muted">Exit: <span className="text-white">{sides.exit}</span></p>
                      <p className="text-muted">Entry Px: <span className="text-white">{fmt(t.entry_price)}</span></p>
                      <p className="text-muted">Exit Px: <span className="text-white">{fmt(t.exit_price)}</span></p>
                      <p className="text-muted">Qty: <span className="text-white">{Number(t.quantity || 0).toFixed(5)}</span></p>
                      <p className={`font-bold ${(t.profit || 0) >= 0 ? 'text-accent' : 'text-red'}`}>
                        PnL: {t.profit != null ? `${t.profit >= 0 ? '+' : ''}${fmt(t.profit)}` : '-'}
                      </p>
                    </div>
                    <p className="font-mono text-[10px] text-muted mt-2">{t.reason || '-'}</p>
                  </div>
                )
              })}
            </div>

            <div className="hidden md:block overflow-x-auto">
              <table className="w-full font-mono text-xs min-w-[700px]">
                <thead>
                  <tr className="border-b border-border">
                    {['Date', 'Asset', 'Close Type', 'Entry', 'Entry Price', 'Exit', 'Exit Price', 'Qty', 'Profit', 'AI Reason'].map((h) => (
                      <th key={h} className="pb-3 text-left text-muted tracking-widest uppercase text-[10px] pr-6 last:pr-0">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredTrades.map((t, i) => (
                    (() => {
                      const sides = sideLabels(t.action_type)
                      return (
                    <tr
                      key={t.id}
                      className="border-b border-border/40 hover:bg-border/20 transition group"
                      style={{ animationDelay: `${i * 30}ms` }}
                    >
                      <td className="py-3 pr-6 text-muted whitespace-nowrap">{formatDate(t.timestamp)}</td>
                      <td className="py-3 pr-6 text-accent font-bold">{t.asset}</td>
                      <td className="py-3 pr-6"><ActionLabel actionType={t.action_type} /></td>
                      <td className="py-3 pr-6 text-white">{sides.entry}</td>
                      <td className="py-3 pr-6 text-white">
                        {fmt(t.entry_price)}
                      </td>
                      <td className="py-3 pr-6 text-white">{sides.exit}</td>
                      <td className="py-3 pr-6 text-white">
                        {fmt(t.exit_price)}
                      </td>
                      <td className="py-3 pr-6 text-white">{Number(t.quantity || 0).toFixed(5)}</td>
                      <td className={`py-3 pr-6 font-bold ${(t.profit || 0) >= 0 ? 'text-accent' : 'text-red'}`}>
                        {t.profit != null ? `${t.profit >= 0 ? '+' : ''}${fmt(t.profit)}` : '-'}
                      </td>
                      <td className="py-3 text-muted max-w-[200px] truncate">{t.reason || '-'}</td>
                    </tr>
                      )
                    })()
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Card>

      <Card>
        <CardLabel>Rule Engine Log</CardLabel>
        {loading ? (
          <div className="flex justify-center py-8"><Spinner size={24} /></div>
        ) : ruleLogs.length === 0 ? (
          <p className="font-mono text-xs text-muted mt-3">No rule events yet.</p>
        ) : (
          <div className="mt-4 space-y-3">
            <div className="grid grid-cols-1 gap-3 md:hidden">
              {ruleLogs.map((log) => (
                <div key={log.id} className="rounded-lg border border-border bg-bg px-4 py-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-mono text-xs text-yellow font-bold">{log.event_type || '-'}</p>
                    <p className="font-mono text-[10px] text-muted">{formatDate(log.timestamp)}</p>
                  </div>
                  <p className="font-mono text-[11px] text-accent mt-2">{log.asset || '-'}</p>
                  <p className="font-mono text-[11px] text-white mt-1">Decision: {log.decision || '-'}</p>
                  <p className="font-mono text-[10px] text-muted mt-2">{log.reason || '-'}</p>
                </div>
              ))}
            </div>

            <div className="hidden md:block overflow-x-auto">
              <table className="w-full font-mono text-xs min-w-[700px]">
                <thead>
                  <tr className="border-b border-border">
                    {['Date', 'Asset', 'Type', 'Decision', 'Reason'].map((h) => (
                      <th key={h} className="pb-3 text-left text-muted tracking-widest uppercase text-[10px] pr-6 last:pr-0">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {ruleLogs.map((log) => (
                    <tr key={log.id} className="border-b border-border/40 hover:bg-border/20 transition">
                      <td className="py-3 pr-6 text-muted whitespace-nowrap">{formatDate(log.timestamp)}</td>
                      <td className="py-3 pr-6 text-accent font-bold">{log.asset || '-'}</td>
                      <td className="py-3 pr-6 text-yellow">{log.event_type || '-'}</td>
                      <td className="py-3 pr-6 text-white">{log.decision || '-'}</td>
                      <td className="py-3 text-muted">{log.reason || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}

import { useState, useEffect, useCallback } from 'react'
import { TrendingUp, TrendingDown, Minus, RefreshCw, Play, Brain, Pause, Activity } from 'lucide-react'
import Card, { CardLabel, CardValue } from '../components/Card'
import PortfolioChart from '../components/Chart'
import Spinner from '../components/Spinner'
import {
  runTrade,
  getPortfolio,
  getHistory,
  getSettings,
  getAutoTradeStatus,
  startAutoTrade,
  stopAutoTrade,
  getQuotes,
  getPerformanceReport,
  API_BASE_URL,
} from '../api'

const DECISION_CONFIG = {
  BUY: { color: 'text-accent', bg: 'bg-accent/10 border-accent/25', Icon: TrendingUp },
  SELL: { color: 'text-red', bg: 'bg-red/10 border-red/25', Icon: TrendingDown },
  HOLD: { color: 'text-yellow', bg: 'bg-yellow/10 border-yellow/25', Icon: Minus },
  SKIP: { color: 'text-muted', bg: 'bg-border/40 border-border', Icon: Minus },
}

function buildPortfolioChartData(trades) {
  if (!trades.length) return []
  let balance = 100_000
  const points = [{ label: 'Start', value: balance }]

  // Use the recorded profit field rather than recalculating from price x qty,
  // which was incorrect for BUY trades.
  ;[...trades].reverse().forEach((t) => {
    balance += (t.profit || 0)
    const date = new Date(t.timestamp)
    points.push({ label: `${date.getMonth() + 1}/${date.getDate()}`, value: Math.round(balance) })
  })

  return points
}

function formatStatusTime(value) {
  if (!value) return 'Never'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString('en-IN', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
}

export default function Dashboard() {
  const [portfolio, setPortfolio] = useState(null)
  const [lastTrade, setLastTrade] = useState(null)
  const [portfolioChartData, setPortfolioChartData] = useState([])
  const [liveChartData, setLiveChartData] = useState([])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const [asset, setAsset] = useState('RELIANCE.NS')
  const [assets, setAssets] = useState(['RELIANCE.NS', 'TCS.NS'])
  const [runResult, setRunResult] = useState(null)
  const [autoStatus, setAutoStatus] = useState(null)
  const [quotes, setQuotes] = useState({})
  const [performance, setPerformance] = useState(null)
  const [refreshing, setRefreshing] = useState(false)

  const fullRefresh = useCallback(async (options = {}) => {
    const { silent = false } = options
    if (silent) setRefreshing(true)
    else setLoading(true)
    setError('')
    try {
      const [pRes, hRes, sRes, aRes, perfRes] = await Promise.all([
        getPortfolio(),
        getHistory(100),
        getSettings(),
        getAutoTradeStatus(),
        getPerformanceReport(1000),
      ])

      setPortfolio(pRes.data)
      const trades = hRes.data.trades || []
      setLastTrade(trades[0] || null)
      setPortfolioChartData(buildPortfolioChartData(trades))

      const cfg = sRes.data || {}
      const resolvedAssets = (cfg.assets || []).length ? cfg.assets : (aRes.data.assets || ['RELIANCE.NS'])
      setAssets(resolvedAssets)
      if (!resolvedAssets.includes(asset)) setAsset(resolvedAssets[0])
      setAutoStatus(aRes.data)
      setPerformance(perfRes.data || null)
    } catch {
      const target = API_BASE_URL || 'VITE_API_URL not configured'
      setError(`Backend unreachable at ${target}.`)
    } finally {
      if (silent) setRefreshing(false)
      else setLoading(false)
    }
  }, [asset])

  const fastRefresh = useCallback(async () => {
    try {
      const [quoteRes, portfolioRes, statusRes] = await Promise.all([
        getQuotes(asset ? [asset] : []),
        getPortfolio(),
        getAutoTradeStatus(),
      ])
      const nextQuotes = quoteRes.data?.quotes || {}
      setQuotes(nextQuotes)
      setPortfolio(portfolioRes.data)
      setAutoStatus(statusRes.data)

      const q = nextQuotes[asset]
      if (q?.price != null) {
        const stamp = new Date().toLocaleTimeString('en-US', { hour12: false })
        setLiveChartData((prev) => [...prev.slice(-39), { label: stamp, value: Number(q.price) }])
      }
    } catch {
      // Keep UI calm during transient quote failures.
    }
  }, [asset])

  useEffect(() => {
    fullRefresh()
  }, [fullRefresh])

  useEffect(() => {
    const id = setInterval(fastRefresh, 3000)
    return () => clearInterval(id)
  }, [fastRefresh])

  const handleRun = async () => {
    setRunning(true)
    setError('')
    setRunResult(null)
    try {
      const res = await runTrade()
      setRunResult(res.data)
      await fullRefresh()
    } catch (e) {
      setError(e?.response?.data?.detail || 'Trade failed. Check API key and backend.')
    } finally {
      setRunning(false)
    }
  }

  const toggleAutoTrade = async () => {
    setError('')
    try {
      if (autoStatus?.running) await stopAutoTrade()
      else await startAutoTrade()
      await fullRefresh()
    } catch (e) {
      setError(e?.response?.data?.detail || 'Unable to change auto trade state.')
    }
  }

  const fmt = (n) =>
    n != null
      ? `Rs ${Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      : '-'

  const pnl = portfolio ? portfolio.total_pnl : null
  const pnlColor = pnl == null ? 'text-muted' : pnl >= 0 ? 'text-accent' : 'text-red'
  const dc = lastTrade ? (DECISION_CONFIG[lastTrade.decision] || DECISION_CONFIG.HOLD) : null
  const live = quotes[asset] || null
  const cycleResults = Array.isArray(runResult?.results) ? runResult.results : []
  const skippedResults = cycleResults.filter((item) => item.skipped)
  const executedResults = cycleResults.filter((item) => !item.skipped && ['BUY', 'SELL'].includes(item.decision))
  const perfWinRate =
    performance?.win_rate != null ? `${(Number(performance.win_rate) * 100).toFixed(1)}%` : '-'
  const perfProfitFactor =
    performance?.profit_factor != null ? String(performance.profit_factor) : '-'
  const perfExpectancy = performance?.expectancy_per_trade != null ? fmt(performance.expectancy_per_trade) : '-'
  const perfRealized = performance?.realized_pnl_window != null ? fmt(performance.realized_pnl_window) : '-'
  const perfRealizedColor =
    performance?.realized_pnl_window == null
      ? 'text-muted'
      : Number(performance.realized_pnl_window) >= 0
        ? 'text-accent'
        : 'text-red'
  const dailyRealizedData = (performance?.daily_realized_last_7d || []).map((point) => ({
    label: point.label || point.date || '',
    value: Number(point.realized_pnl || 0),
  }))
  const dailyRealizedTotal7d = dailyRealizedData.reduce((acc, p) => acc + Number(p.value || 0), 0)
  const dailyTrendColor = dailyRealizedTotal7d >= 0 ? '#00ff87' : '#ff4d5a'
  const dailyTrendTextColor = dailyRealizedTotal7d >= 0 ? 'text-accent' : 'text-red'

  return (
    <div className="animate-fade-in space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="font-sans font-800 text-2xl sm:text-3xl text-white tracking-tight">Dashboard</h1>
          <p className="font-mono text-[11px] text-muted mt-1 tracking-widest">LIVE PAPER TRADING OVERVIEW</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => fullRefresh({ silent: true })}
            disabled={loading}
            className="btn-ghost"
          >
            {loading || refreshing ? <Spinner size={13} /> : <RefreshCw size={13} />}
            Refresh
          </button>
          <button
            type="button"
            onClick={handleRun}
            disabled={running}
            className="btn-primary"
          >
            {running ? <Spinner size={13} /> : <Play size={13} />}
            {running ? 'Running...' : 'Run Universe Cycle'}
          </button>
          <button
            type="button"
            onClick={toggleAutoTrade}
            className={autoStatus?.running ? 'btn-outline-danger' : 'btn-outline-accent'}
          >
            {autoStatus?.running ? <Pause size={13} /> : <Activity size={13} />}
            {autoStatus?.running ? 'Stop Auto' : 'Start Auto'}
          </button>
        </div>
      </div>

      {autoStatus && (
        <Card className="border-border/70">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <CardLabel>Session &amp; loop</CardLabel>
              <p className="font-mono text-[10px] text-muted/80 mt-1 max-w-prose">
                Market gate, scan size, and last auto-cycle status. Indicator data is free/delayed — treat as simulation only.
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span
                className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[10px] font-bold tracking-wide ${
                  autoStatus.running
                    ? 'border-accent/30 bg-accent/10 text-accent'
                    : 'border-border text-muted'
                }`}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${autoStatus.running ? 'bg-accent animate-pulse' : 'bg-muted'}`} />
                {autoStatus.running ? 'AUTO ON' : 'AUTO OFF'}
              </span>
            </div>
          </div>
          <div className="mt-4 grid gap-x-8 gap-y-2 font-mono text-[11px] text-muted sm:grid-cols-2 lg:grid-cols-3">
            <span>Loop: <span className="text-white">{autoStatus.interval_seconds}s</span></span>
            <span>Universe: <span className="text-white">{autoStatus.stock_universe_label || autoStatus.stock_universe}</span></span>
            <span>Universe stocks: <span className="text-white">{autoStatus.universe_asset_count ?? (autoStatus.assets || []).length}</span></span>
            <span>Cycle stocks: <span className="text-white">{autoStatus.cycle_asset_count ?? '-'}</span></span>
            <span>Watchlist only: <span className="text-white">{autoStatus.watchlist_only ? 'ON' : 'OFF'}</span></span>
            <span>Max/cycle: <span className="text-white">{autoStatus.max_symbols_per_cycle || 'ALL'}</span></span>
            <span>Fresh-data gate: <span className="text-white">{autoStatus.require_fresh_indicators ? 'ON' : 'OFF'}</span></span>
            <span>
              Session:{' '}
              <span className={autoStatus.nse_session_open ? 'text-accent' : 'text-yellow'}>
                {autoStatus.nse_session_open ? 'OPEN' : 'CLOSED'}
              </span>
            </span>
            <span>Last cycle: <span className="text-white">{formatStatusTime(autoStatus.last_run_at)}</span></span>
            {autoStatus.nse_session_detail && (
              <span className="sm:col-span-2 lg:col-span-3 text-muted/90">
                {autoStatus.nse_session_detail}
              </span>
            )}
            {refreshing && <span className="text-blue sm:col-span-2">Refreshing live quotes…</span>}
            {autoStatus.last_error && (
              <span className="text-yellow sm:col-span-2 lg:col-span-3">
                Last note: {autoStatus.last_error}
              </span>
            )}
          </div>
        </Card>
      )}

      {error && (
        <div
          role="alert"
          className="rounded-2xl border border-red/35 bg-red/[0.06] px-4 py-3 font-mono text-xs text-red shadow-sm shadow-black/20"
        >
          {error}
        </div>
      )}

      {runResult && !error && (
        <div className="rounded-2xl border border-accent/30 bg-accent/[0.06] px-4 py-3 font-mono text-xs text-accent shadow-sm shadow-black/20 animate-slide-up">
          {Array.isArray(runResult.results)
            ? `OK Cycle complete: ${runResult.executed_trades || 0} trades executed, ${runResult.skipped_assets || 0} skipped, across ${runResult.total_assets || 0} stocks.`
            : `OK ${runResult.decision} ${runResult.asset} @ ${fmt(runResult.price)} - ${runResult.reason}`}
          {!Array.isArray(runResult.results) && runResult.skipped && (
            <span className="text-yellow ml-2">({runResult.skip_reason})</span>
          )}
        </div>
      )}

      {Array.isArray(runResult?.results) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card>
            <div className="flex items-center justify-between mb-4">
              <div>
                <CardLabel>Executed This Cycle</CardLabel>
                <p className="font-mono text-[10px] text-muted mt-1">{executedResults.length} trade actions</p>
              </div>
            </div>
            {executedResults.length === 0 ? (
              <p className="font-mono text-xs text-muted">No BUY or SELL orders were executed in the last cycle.</p>
            ) : (
              <div className="space-y-3">
                {executedResults.slice(0, 8).map((item) => (
                  <div key={`${item.asset}-${item.decision}`} className="rounded-lg border border-accent/20 bg-accent/5 px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-mono text-xs text-accent font-bold">{item.asset}</p>
                      <span className={`font-mono text-[10px] ${item.decision === 'BUY' ? 'text-accent' : 'text-red'}`}>
                        {item.decision}
                      </span>
                    </div>
                    <p className="font-mono text-[11px] text-white mt-1">{fmt(item.price)}</p>
                    <p className="font-mono text-[10px] text-muted mt-2">{item.reason || 'No reason provided.'}</p>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card>
            <div className="flex items-center justify-between mb-4">
              <div>
                <CardLabel>Skipped This Cycle</CardLabel>
                <p className="font-mono text-[10px] text-muted mt-1">Top skip reasons from the latest run</p>
              </div>
            </div>
            {skippedResults.length === 0 ? (
              <p className="font-mono text-xs text-muted">Nothing was skipped in the last cycle.</p>
            ) : (
              <div className="space-y-3">
                {skippedResults.slice(0, 8).map((item, index) => (
                  <div key={`${item.asset}-${index}`} className="rounded-lg border border-border bg-bg px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-mono text-xs text-white font-bold">{item.asset}</p>
                      <span className="font-mono text-[10px] text-yellow">{item.decision || 'SKIP'}</span>
                    </div>
                    <p className="font-mono text-[10px] text-muted mt-2">{item.skip_reason || item.reason || 'No skip reason provided.'}</p>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <Card glow>
          <CardLabel>Live Price ({asset})</CardLabel>
          <CardValue>{live?.price != null ? fmt(live.price) : '-'}</CardValue>
          <p className={`font-mono text-[10px] mt-2 ${(live?.change || 0) >= 0 ? 'text-accent' : 'text-red'}`}>
            {live ? `${live.change >= 0 ? '+' : ''}${Number(live.change).toFixed(2)} (${live.change_percent >= 0 ? '+' : ''}${Number(live.change_percent).toFixed(2)}%)` : 'Waiting for quote...'}
          </p>
        </Card>
        <Card glow>
          <CardLabel>Total Equity</CardLabel>
          <CardValue>{loading ? '-' : fmt(portfolio?.total_equity)}</CardValue>
          <p className="font-mono text-[10px] text-muted mt-2">Cash + live position value</p>
        </Card>
        <Card glow>
          <CardLabel>Cash Available</CardLabel>
          <CardValue className="text-blue">{loading ? '-' : fmt(portfolio?.cash_balance)}</CardValue>
          <p className="font-mono text-[10px] text-muted mt-2">Uninvested funds</p>
        </Card>
        <Card glow>
          <CardLabel>Total PnL</CardLabel>
          <CardValue className={pnlColor}>{loading ? '-' : (pnl >= 0 ? '+' : '') + fmt(pnl)}</CardValue>
          <p className="font-mono text-[10px] text-muted mt-2">Unrealized: {fmt(portfolio?.unrealized_pnl)}</p>
        </Card>
      </div>

      <Card>
        <div className="flex items-center justify-between mb-4">
          <div>
            <CardLabel>Forward Test Performance (Paper)</CardLabel>
            <p className="font-mono text-[10px] text-muted mt-1">
              Latest {performance?.window_trades ?? '-'} trades, {performance?.window_closed_trades ?? '-'} closes
            </p>
          </div>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="border border-border rounded-lg px-4 py-3 bg-bg">
            <p className="font-mono text-[10px] text-muted tracking-widest uppercase">Win Rate</p>
            <p className="font-mono text-lg font-bold text-white mt-1">{perfWinRate}</p>
          </div>
          <div className="border border-border rounded-lg px-4 py-3 bg-bg">
            <p className="font-mono text-[10px] text-muted tracking-widest uppercase">Profit Factor</p>
            <p className="font-mono text-lg font-bold text-white mt-1">{perfProfitFactor}</p>
          </div>
          <div className="border border-border rounded-lg px-4 py-3 bg-bg">
            <p className="font-mono text-[10px] text-muted tracking-widest uppercase">Expectancy / Trade</p>
            <p className="font-mono text-lg font-bold text-white mt-1">{perfExpectancy}</p>
          </div>
          <div className="border border-border rounded-lg px-4 py-3 bg-bg">
            <p className="font-mono text-[10px] text-muted tracking-widest uppercase">Realized PnL</p>
            <p className={`font-mono text-lg font-bold mt-1 ${perfRealizedColor}`}>{perfRealized}</p>
          </div>
        </div>
      </Card>

      <Card>
        <div className="flex items-center justify-between mb-4">
          <div>
            <CardLabel>Daily Realized PnL (Last 7 Days)</CardLabel>
            <p className="font-mono text-[10px] text-muted mt-1">Paper-trade realized outcomes by day</p>
          </div>
          <span className={`font-mono text-xs font-bold ${dailyTrendTextColor}`}>
            7D Total: {dailyRealizedTotal7d >= 0 ? '+' : ''}{fmt(dailyRealizedTotal7d)}
          </span>
        </div>
        <PortfolioChart
          data={dailyRealizedData}
          color={dailyTrendColor}
          gradientId="daily-pnl-grad"
        />
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <div className="flex items-center justify-between gap-3 mb-4">
            <div>
              <CardLabel>Live Asset Chart</CardLabel>
              <p className="font-sans font-600 text-white text-base">{asset} (updates every 3s)</p>
            </div>
            <select
              value={asset}
              onChange={(e) => setAsset(e.target.value)}
              className="field-control px-3 py-2"
            >
              {assets.map((a) => (
                <option key={a} value={a}>{a}</option>
              ))}
            </select>
          </div>
          <PortfolioChart data={liveChartData} />
        </Card>

        <Card>
          <div className="flex items-center justify-between mb-4">
            <div>
              <CardLabel>Portfolio Value</CardLabel>
              <p className="font-sans font-600 text-white text-base">Balance Over Trades</p>
            </div>
            <span className={`font-mono text-xs font-bold ${pnlColor}`}>
              {pnl != null ? `${pnl >= 0 ? 'UP' : 'DOWN'} ${fmt(Math.abs(pnl))}` : ''}
            </span>
          </div>
          <PortfolioChart data={portfolioChartData} />
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-1">
          <div className="flex items-center gap-2 mb-4">
            <Brain size={14} className="text-accent" />
            <span className="font-mono text-[10px] text-muted tracking-widest uppercase">Last AI Decision</span>
          </div>
          {!lastTrade ? (
            <p className="font-mono text-xs text-muted">No trades yet.</p>
          ) : (() => {
            const { color, bg, Icon } = dc
            return (
              <>
                <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border font-mono text-sm font-bold mb-4 ${color} ${bg}`}>
                  <Icon size={14} />
                  {lastTrade.decision}
                </div>
                <div className="space-y-3">
                  <div><CardLabel>Asset</CardLabel><p className="font-mono text-sm text-white">{lastTrade.asset}</p></div>
                  <div><CardLabel>Reason</CardLabel><p className="font-mono text-[11px] text-muted mt-1">{lastTrade.reason}</p></div>
                  <div><CardLabel>Price</CardLabel><p className="font-mono text-sm text-white">{fmt(lastTrade.price)}</p></div>
                </div>
              </>
            )
          })()}
        </Card>

        <Card className="lg:col-span-2">
          <CardLabel>Open Positions</CardLabel>
          {portfolio?.positions?.length > 0 ? (
            <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
              {portfolio.positions.map((pos) => (
                <div key={pos.asset} className="border border-accent/20 bg-accent/5 rounded-lg px-4 py-3">
                  <p className="font-mono text-xs text-accent font-bold">{pos.asset}</p>
                  <p className="font-mono text-[11px] text-muted mt-1">Qty: {Number(pos.quantity).toFixed(6)}</p>
                  <p className="font-mono text-[11px] text-muted">Avg: {fmt(pos.avg_cost)}</p>
                  <p className="font-mono text-[11px] text-muted">Last: {pos.last_price != null ? fmt(pos.last_price) : '-'}</p>
                  <p className="font-mono text-[10px] text-muted">Source: {pos.price_source || 'unknown'}</p>
                  <p className={`font-mono text-[11px] mt-1 ${(pos.unrealized_pnl || 0) >= 0 ? 'text-accent' : 'text-red'}`}>
                    Unrealized: {(pos.unrealized_pnl || 0) >= 0 ? '+' : ''}{fmt(pos.unrealized_pnl || 0)}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p className="font-mono text-xs text-muted mt-3">No open positions.</p>
          )}
        </Card>
      </div>
    </div>
  )
}

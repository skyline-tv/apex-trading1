import { useState, useEffect } from 'react'
import { Wallet as WalletIcon, Landmark, TrendingUp, BarChart2, RefreshCw, RotateCcw } from 'lucide-react'
import Card, { CardLabel } from '../components/Card'
import Spinner from '../components/Spinner'
import { getPortfolio, resetWallet, API_BASE_URL } from '../api'

export default function Wallet() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [resetting, setResetting] = useState(false)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')

  const fetch = async (options = {}) => {
    const { silent = false } = options
    if (!silent) setLoading(true)
    setError('')
    try {
      const res = await getPortfolio()
      setData(res.data)
    } catch {
      const target = API_BASE_URL || 'VITE_API_URL not configured'
      setError(`Cannot reach backend at ${target}`)
    } finally {
      if (!silent) setLoading(false)
    }
  }

  useEffect(() => {
    fetch()
    const id = setInterval(() => fetch({ silent: true }), 10_000)
    return () => clearInterval(id)
  }, [])

  const handleReset = async () => {
    if (!confirm('Reset wallet to Rs 100,000 and clear all trades?')) return
    setResetting(true)
    try {
      await resetWallet()
      setMsg('Wallet reset successfully.')
      await fetch()
    } catch {
      setError('Reset failed.')
    } finally {
      setResetting(false)
    }
  }

  const fmt = (n) =>
    n != null
      ? `Rs ${Number(n).toLocaleString('en-IN', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })}`
      : '-'

  const pnl = data?.total_pnl ?? 0
  const pnlPct = data ? ((pnl / 100_000) * 100).toFixed(2) : '0.00'
  const pnlColor = pnl >= 0 ? 'text-accent' : 'text-red'

  const stats = [
    { label: 'Starting Balance', value: fmt(100_000), icon: Landmark, color: 'text-blue' },
    { label: 'Total Equity', value: fmt(data?.total_equity), icon: WalletIcon, color: 'text-white' },
    { label: 'Cash Balance', value: fmt(data?.cash_balance), icon: WalletIcon, color: 'text-blue' },
    {
      label: 'Total P&L',
      value: (pnl >= 0 ? '+' : '') + fmt(pnl) + ` (${pnlPct}%)`,
      icon: TrendingUp,
      color: pnlColor,
    },
    { label: 'Trades Executed', value: data?.trade_count ?? 0, icon: BarChart2, color: 'text-yellow' },
  ]

  return (
    <div className="animate-fade-in space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="font-sans font-800 text-2xl sm:text-3xl text-white tracking-tight">Wallet</h1>
          <p className="font-mono text-[11px] text-muted mt-0.5 tracking-widest">
            VIRTUAL ACCOUNT - RS 100,000 STARTING CAPITAL
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={fetch} className="btn-ghost">
            {loading ? <Spinner size={13} /> : <RefreshCw size={13} />}
            Refresh
          </button>
          <button type="button" onClick={handleReset} disabled={resetting} className="btn-outline-danger">
            {resetting ? <Spinner size={13} /> : <RotateCcw size={13} />}
            Reset
          </button>
        </div>
      </div>

      {error && (
        <div role="alert" className="rounded-2xl border border-red/35 bg-red/[0.06] px-4 py-3 font-mono text-xs text-red shadow-sm shadow-black/20">
          {error}
        </div>
      )}
      {msg && (
        <div className="rounded-2xl border border-accent/30 bg-accent/[0.06] px-4 py-3 font-mono text-xs text-accent shadow-sm shadow-black/20">
          {msg}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {stats.map(({ label, value, icon: Icon, color }) => (
          <Card key={label} glow>
            <div className="flex items-start justify-between">
              <div>
                <CardLabel>{label}</CardLabel>
                <p className={`font-mono text-2xl font-bold mt-1 ${color}`}>{value}</p>
              </div>
              <div className="p-2 rounded-lg bg-border/50">
                <Icon size={16} className={color} />
              </div>
            </div>
          </Card>
        ))}
      </div>

      <Card>
        <CardLabel>Open Positions</CardLabel>
        {loading ? (
          <div className="flex justify-center py-8"><Spinner size={24} /></div>
        ) : !data?.positions || data.positions.length === 0 ? (
          <p className="font-mono text-xs text-muted mt-3">No open positions.</p>
        ) : (
          <div className="mt-4 space-y-3">
            <div className="grid grid-cols-1 gap-3 md:hidden">
              {data.positions.map((p) => (
                <div key={p.asset} className="rounded-lg border border-border bg-bg px-4 py-3">
                  <div className="flex items-center justify-between">
                    <p className="font-mono text-xs text-accent font-bold">{p.asset}</p>
                    <p className={`font-mono text-xs font-bold ${(p.unrealized_pnl || 0) >= 0 ? 'text-accent' : 'text-red'}`}>
                      {(p.unrealized_pnl || 0) >= 0 ? '+' : ''}{fmt(p.unrealized_pnl || 0)}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-2 font-mono text-[11px]">
                    <p className="text-muted">Qty: <span className="text-white">{Number(p.quantity).toFixed(6)}</span></p>
                    <p className="text-muted">Avg: <span className="text-white">{fmt(p.avg_cost)}</span></p>
                    <p className="text-muted">Last: <span className="text-white">{p.last_price != null ? fmt(p.last_price) : '-'}</span></p>
                    <p className="text-muted">Source: <span className="text-white">{p.price_source || '-'}</span></p>
                  </div>
                </div>
              ))}
            </div>

            <div className="hidden md:block overflow-x-auto">
              <table className="w-full font-mono text-xs">
                <thead>
                  <tr className="border-b border-border">
                    {['Asset', 'Quantity', 'Avg Cost', 'Last Price', 'Unrealized P&L'].map((h) => (
                      <th key={h} className="pb-2 text-left text-muted tracking-widest uppercase text-[10px] pr-8">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.positions.map((p) => (
                    <tr key={p.asset} className="border-b border-border/50 hover:bg-border/20 transition">
                      <td className="py-3 text-accent font-bold pr-8">{p.asset}</td>
                      <td className="py-3 text-white pr-8">{Number(p.quantity).toFixed(6)}</td>
                      <td className="py-3 text-white pr-8">{fmt(p.avg_cost)}</td>
                      <td className="py-3 text-white pr-8">{p.last_price != null ? fmt(p.last_price) : '-'}</td>
                      <td className={`py-3 pr-8 font-bold ${(p.unrealized_pnl || 0) >= 0 ? 'text-accent' : 'text-red'}`}>
                        {(p.unrealized_pnl || 0) >= 0 ? '+' : ''}{fmt(p.unrealized_pnl || 0)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Card>

      {data && (
        <Card>
          <CardLabel>Performance</CardLabel>
          <div className="mt-3 space-y-3">
            <div className="flex justify-between font-mono text-xs text-muted">
              <span>Rs 0</span>
              <span className={pnlColor}>{pnl >= 0 ? '+' : ''}{pnlPct}%</span>
              <span>Rs 100k</span>
            </div>
            <div className="h-2 bg-border rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-700 ${pnl >= 0 ? 'bg-accent' : 'bg-red'}`}
                style={{ width: `${Math.min(100, Math.max(0, ((data.total_equity || 0) / 200_000) * 100))}%` }}
              />
            </div>
            <p className="font-mono text-[10px] text-muted">
              Balance relative to max tracked value (Rs 200k ceiling for display)
            </p>
          </div>
        </Card>
      )}
    </div>
  )
}

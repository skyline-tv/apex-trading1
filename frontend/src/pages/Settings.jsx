import { useState, useEffect } from 'react'
import { Save, RefreshCw, Settings as SettingsIcon } from 'lucide-react'
import Card from '../components/Card'
import Spinner from '../components/Spinner'
import { getSettings, saveSettings, API_BASE_URL } from '../api'

const FIELD_OPTIONS = {
  stock_universe: [
    { value: 'nifty_50', label: 'Nifty 50 (NSE Flagship)' },
    { value: 'sensex', label: 'S&P BSE Sensex (BSE Flagship)' },
    { value: 'nifty_bank', label: 'Nifty Bank (Banking Sector Benchmark)' },
    { value: 'nifty_next_50', label: 'Nifty Next 50 (Upcoming Bluechips)' },
    { value: 'nifty_100', label: 'Nifty 100 (Top 100 Combined)' },
  ],
  style: [
    { value: 'day_trade', label: 'Day Trade' },
    { value: 'short_term', label: 'Short Term' },
    { value: 'long_term', label: 'Long Term' },
  ],
  risk: [
    { value: 'low', label: 'Low' },
    { value: 'medium', label: 'Medium' },
    { value: 'high', label: 'High' },
  ],
}

function Select({ label, value, onChange, options }) {
  return (
    <div>
      <label className="block font-mono text-[10px] text-muted tracking-widest uppercase mb-2">
        {label}
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-bg border border-border text-white font-mono text-sm px-4 py-3 rounded-lg focus:outline-none focus:border-accent/60 transition"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  )
}

function NumberInput({ label, value, onChange, min, max, step = 1 }) {
  return (
    <div>
      <label className="block font-mono text-[10px] text-muted tracking-widest uppercase mb-2">
        {label}
      </label>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        min={min}
        max={max}
        step={step}
        className="w-full bg-bg border border-border text-white font-mono text-sm px-4 py-3 rounded-lg focus:outline-none focus:border-accent/60 transition"
      />
    </div>
  )
}

export default function Settings() {
  const [form, setForm] = useState({
    market: 'indian_stocks',
    stock_universe: 'nifty_50',
    style: 'short_term',
    risk: 'medium',
    trade_amount: 10000,
    risk_per_trade_pct: 0.01,
    min_confidence: 60,
    max_daily_loss_pct: 0.03,
    max_open_positions: 8,
    max_trades_per_day: 30,
    loss_streak_cooldown: 3,
    cooldown_minutes: 30,
    stop_loss_pct: 0.015,
    take_profit_pct: 0.03,
    min_rr: 1.5,
    max_holding_minutes_day_trade: 180,
    no_averaging_down: true,
    rsi_min: 0,
    rsi_max: 100,
    min_price: 0,
    max_price: 1000000,
    min_volume: 0,
    require_uptrend: false,
    auto_start: false,
    respect_market_hours: true,
    watchlist_only: false,
    max_symbols_per_cycle: 20,
    require_fresh_indicators: true,
    loop_interval_seconds: 20,
    execution_slippage_bps: 5,
    brokerage_fee_bps: 2,
    fixed_fee_per_order: 0,
    assets: [],
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await getSettings()
      setForm((prev) => ({ ...prev, ...(res.data || {}) }))
    } catch {
      const target = API_BASE_URL || 'VITE_API_URL not configured'
      setError(`Cannot reach backend at ${target}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const set = (key) => (val) => setForm((prev) => ({ ...prev, [key]: val }))

  const handleSave = async () => {
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      const payload = {
        stock_universe: form.stock_universe,
        style: form.style,
        risk: form.risk,
        trade_amount: Number(form.trade_amount),
        risk_per_trade_pct: Number(form.risk_per_trade_pct),
        min_confidence: Number(form.min_confidence),
        max_daily_loss_pct: Number(form.max_daily_loss_pct),
        max_open_positions: Number(form.max_open_positions),
        max_trades_per_day: Number(form.max_trades_per_day),
        loss_streak_cooldown: Number(form.loss_streak_cooldown),
        cooldown_minutes: Number(form.cooldown_minutes),
        stop_loss_pct: Number(form.stop_loss_pct),
        take_profit_pct: Number(form.take_profit_pct),
        min_rr: Number(form.min_rr),
        max_holding_minutes_day_trade: Number(form.max_holding_minutes_day_trade),
        no_averaging_down: Boolean(form.no_averaging_down),
        rsi_min: Number(form.rsi_min),
        rsi_max: Number(form.rsi_max),
        min_price: Number(form.min_price),
        max_price: Number(form.max_price),
        min_volume: Number(form.min_volume),
        require_uptrend: Boolean(form.require_uptrend),
        auto_start: Boolean(form.auto_start),
        respect_market_hours: Boolean(form.respect_market_hours),
        watchlist_only: Boolean(form.watchlist_only),
        max_symbols_per_cycle: Number(form.max_symbols_per_cycle),
        require_fresh_indicators: Boolean(form.require_fresh_indicators),
        loop_interval_seconds: Number(form.loop_interval_seconds),
        execution_slippage_bps: Number(form.execution_slippage_bps),
        brokerage_fee_bps: Number(form.brokerage_fee_bps),
        fixed_fee_per_order: Number(form.fixed_fee_per_order),
      }
      const res = await saveSettings(payload)
      setForm((prev) => ({ ...prev, ...(res.data?.settings || {}) }))
      setSuccess('Settings saved. The agent now scans and filters all stocks in the selected universe each cycle.')
    } catch (e) {
      setError(e?.response?.data?.detail || 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="animate-fade-in space-y-6 max-w-2xl">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="font-sans font-800 text-2xl text-white tracking-tight">Settings</h1>
          <p className="font-mono text-[11px] text-muted mt-0.5 tracking-widest">
            INDIAN MARKET AI CONFIG
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border text-muted hover:text-white hover:border-white/20 transition font-mono text-xs"
        >
          {loading ? <Spinner size={13} /> : <RefreshCw size={13} />}
          Reload
        </button>
      </div>

      {error && <div className="border border-red/30 bg-red/5 rounded-xl px-4 py-3 font-mono text-xs text-red">{error}</div>}
      {success && <div className="border border-accent/30 bg-accent/5 rounded-xl px-4 py-3 font-mono text-xs text-accent">{success}</div>}

      {loading ? (
        <div className="flex justify-center py-16"><Spinner size={32} /></div>
      ) : (
        <>
          <Card>
            <div className="flex items-center gap-2 mb-5">
              <SettingsIcon size={13} className="text-accent" />
              <span className="font-mono text-[10px] text-muted tracking-widest uppercase">Universe Selection</span>
            </div>
            <div className="space-y-5">
              <Select label="Index Universe" value={form.stock_universe} onChange={set('stock_universe')} options={FIELD_OPTIONS.stock_universe} />
              <Select label="Trading Style" value={form.style} onChange={set('style')} options={FIELD_OPTIONS.style} />
              <Select label="Risk Level" value={form.risk} onChange={set('risk')} options={FIELD_OPTIONS.risk} />
            </div>
          </Card>

          <Card>
            <span className="font-mono text-[10px] text-muted tracking-widest uppercase">Trade Parameters</span>
            <div className="space-y-5 mt-5">
              <NumberInput label="Trade Amount (Rs Notional per Buy)" value={form.trade_amount} onChange={set('trade_amount')} min={100} max={1000000} step={100} />
              <NumberInput label="Auto Trade Interval (seconds)" value={form.loop_interval_seconds} onChange={set('loop_interval_seconds')} min={5} max={300} step={1} />
              <NumberInput
                label="Max Symbols Per Cycle (0 = no cap)"
                value={form.max_symbols_per_cycle}
                onChange={set('max_symbols_per_cycle')}
                min={0}
                max={200}
                step={1}
              />
            </div>
          </Card>

          <Card>
            <span className="font-mono text-[10px] text-muted tracking-widest uppercase">Paper Trade Realism</span>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-5">
              <NumberInput
                label="Execution Slippage (bps)"
                value={form.execution_slippage_bps}
                onChange={set('execution_slippage_bps')}
                min={0}
                max={100}
                step={0.1}
              />
              <NumberInput
                label="Brokerage / Fees (bps)"
                value={form.brokerage_fee_bps}
                onChange={set('brokerage_fee_bps')}
                min={0}
                max={100}
                step={0.1}
              />
              <NumberInput
                label="Fixed Fee Per Order (Rs)"
                value={form.fixed_fee_per_order}
                onChange={set('fixed_fee_per_order')}
                min={0}
                max={1000}
                step={0.1}
              />
            </div>
          </Card>

          <Card>
            <span className="font-mono text-[10px] text-muted tracking-widest uppercase">Discipline Rules</span>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-5">
              <NumberInput label="Risk Per Trade (pct)" value={form.risk_per_trade_pct} onChange={set('risk_per_trade_pct')} min={0.001} max={0.2} step={0.001} />
              <NumberInput label="Min Confidence (0-100)" value={form.min_confidence} onChange={set('min_confidence')} min={0} max={100} step={1} />
              <NumberInput label="Max Daily Loss (pct)" value={form.max_daily_loss_pct} onChange={set('max_daily_loss_pct')} min={0.001} max={0.5} step={0.001} />
              <NumberInput label="Max Open Positions" value={form.max_open_positions} onChange={set('max_open_positions')} min={1} max={100} step={1} />
              <NumberInput label="Max Trades Per Day" value={form.max_trades_per_day} onChange={set('max_trades_per_day')} min={1} max={500} step={1} />
              <NumberInput label="Loss Streak Cooldown Trigger" value={form.loss_streak_cooldown} onChange={set('loss_streak_cooldown')} min={1} max={20} step={1} />
              <NumberInput label="Cooldown Minutes" value={form.cooldown_minutes} onChange={set('cooldown_minutes')} min={1} max={600} step={1} />
              <NumberInput label="Stop Loss (pct)" value={form.stop_loss_pct} onChange={set('stop_loss_pct')} min={0.001} max={0.2} step={0.001} />
              <NumberInput label="Take Profit (pct)" value={form.take_profit_pct} onChange={set('take_profit_pct')} min={0.001} max={0.5} step={0.001} />
              <NumberInput label="Min Risk/Reward" value={form.min_rr} onChange={set('min_rr')} min={0.1} max={10} step={0.1} />
              <NumberInput label="Max Hold (day trade, min)" value={form.max_holding_minutes_day_trade} onChange={set('max_holding_minutes_day_trade')} min={1} max={1440} step={1} />
            </div>
            <div className="mt-5 flex items-center justify-between border border-border rounded-lg px-4 py-3">
              <div>
                <p className="font-mono text-sm text-white font-bold">No Averaging Down</p>
                <p className="font-mono text-[10px] text-muted mt-1">Blocks adding to losing positions.</p>
              </div>
              <button
                onClick={() => set('no_averaging_down')(!form.no_averaging_down)}
                className={`relative w-12 h-6 rounded-full transition-colors duration-200 ${form.no_averaging_down ? 'bg-accent' : 'bg-border'}`}
              >
                <span
                  className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-transform duration-200 ${form.no_averaging_down ? 'translate-x-7' : 'translate-x-1'}`}
                />
              </button>
            </div>
          </Card>

          <Card>
            <span className="font-mono text-[10px] text-muted tracking-widest uppercase">Filters (Applied To Every Stock)</span>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-5">
              <NumberInput label="RSI Min" value={form.rsi_min} onChange={set('rsi_min')} min={0} max={100} step={1} />
              <NumberInput label="RSI Max" value={form.rsi_max} onChange={set('rsi_max')} min={0} max={100} step={1} />
              <NumberInput label="Min Price" value={form.min_price} onChange={set('min_price')} min={0} max={10000000} step={1} />
              <NumberInput label="Max Price" value={form.max_price} onChange={set('max_price')} min={0} max={10000000} step={1} />
              <NumberInput label="Min Avg Volume (20)" value={form.min_volume} onChange={set('min_volume')} min={0} max={1000000000} step={1000} />
            </div>
            <div className="mt-5 flex items-center justify-between border border-border rounded-lg px-4 py-3">
              <div>
                <p className="font-mono text-sm text-white font-bold">Require Uptrend</p>
                <p className="font-mono text-[10px] text-muted mt-1">Only allow stocks where MA20 is above MA50.</p>
              </div>
              <button
                onClick={() => set('require_uptrend')(!form.require_uptrend)}
                className={`relative w-12 h-6 rounded-full transition-colors duration-200 ${form.require_uptrend ? 'bg-accent' : 'bg-border'}`}
              >
                <span
                  className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-transform duration-200 ${form.require_uptrend ? 'translate-x-7' : 'translate-x-1'}`}
                />
              </button>
            </div>
          </Card>

          <Card>
            <div className="flex items-center justify-between border-b border-border pb-5 mb-5">
              <div>
                <p className="font-mono text-sm text-white font-bold">Respect NSE hours</p>
                <p className="font-mono text-[10px] text-muted mt-1">
                  Mon–Fri 09:15–15:30 IST only. Stops paper trades when the cash market is closed (free data is still stale after hours).
                </p>
              </div>
              <button
                type="button"
                onClick={() => set('respect_market_hours')(!form.respect_market_hours)}
                className={`relative w-12 h-6 rounded-full transition-colors duration-200 ${form.respect_market_hours ? 'bg-accent' : 'bg-border'}`}
              >
                <span
                  className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-transform duration-200 ${form.respect_market_hours ? 'translate-x-7' : 'translate-x-1'}`}
                />
              </button>
            </div>
            <div className="flex items-center justify-between border-b border-border pb-5 mb-5">
              <div>
                <p className="font-mono text-sm text-white font-bold">Require Fresh Indicators</p>
                <p className="font-mono text-[10px] text-muted mt-1">
                  Skip AI decisions when bars are stale/outdated for the selected interval.
                </p>
              </div>
              <button
                type="button"
                onClick={() => set('require_fresh_indicators')(!form.require_fresh_indicators)}
                className={`relative w-12 h-6 rounded-full transition-colors duration-200 ${form.require_fresh_indicators ? 'bg-accent' : 'bg-border'}`}
              >
                <span
                  className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-transform duration-200 ${form.require_fresh_indicators ? 'translate-x-7' : 'translate-x-1'}`}
                />
              </button>
            </div>
            <div className="flex items-center justify-between border-b border-border pb-5 mb-5">
              <div>
                <p className="font-mono text-sm text-white font-bold">Watchlist Only</p>
                <p className="font-mono text-[10px] text-muted mt-1">
                  When ON, cycles scan only symbols listed in settings assets.
                </p>
              </div>
              <button
                type="button"
                onClick={() => set('watchlist_only')(!form.watchlist_only)}
                className={`relative w-12 h-6 rounded-full transition-colors duration-200 ${form.watchlist_only ? 'bg-accent' : 'bg-border'}`}
              >
                <span
                  className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-transform duration-200 ${form.watchlist_only ? 'translate-x-7' : 'translate-x-1'}`}
                />
              </button>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <p className="font-mono text-sm text-white font-bold">Auto Trade Loop</p>
                <p className="font-mono text-[10px] text-muted mt-1">Scans every stock in selected universe each cycle.</p>
              </div>
              <button
                type="button"
                onClick={() => set('auto_start')(!form.auto_start)}
                className={`relative w-12 h-6 rounded-full transition-colors duration-200 ${form.auto_start ? 'bg-accent' : 'bg-border'}`}
              >
                <span
                  className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-transform duration-200 ${form.auto_start ? 'translate-x-7' : 'translate-x-1'}`}
                />
              </button>
            </div>
          </Card>

          <button
            onClick={handleSave}
            disabled={saving}
            className="w-full flex items-center justify-center gap-2 py-3.5 rounded-xl bg-accent text-bg font-sans font-700 text-sm tracking-wider hover:bg-accent/90 transition disabled:opacity-50"
          >
            {saving ? <Spinner size={15} /> : <Save size={15} />}
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
        </>
      )}
    </div>
  )
}

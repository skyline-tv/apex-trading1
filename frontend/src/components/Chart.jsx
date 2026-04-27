import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from 'recharts'

const CustomTooltip = ({ active, payload, label, valuePrefix = 'Rs' }) => {
  if (!active || !payload?.length) return null
  const value = Number(payload[0].value || 0)
  const sign = value > 0 ? '+' : ''
  return (
    <div className="bg-surface border border-border rounded-lg px-3 py-2">
      <p className="font-mono text-[10px] text-muted mb-1">{label}</p>
      <p className="font-mono text-sm text-accent">
        {sign}{valuePrefix} {value.toLocaleString('en-IN')}
      </p>
    </div>
  )
}

export default function PortfolioChart({
  data,
  color = '#00ff87',
  gradientId = 'grad-default',
  valuePrefix = 'Rs',
}) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-muted font-mono text-xs">
        No trade data yet — run your first trade.
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={color} stopOpacity={0.18} />
            <stop offset="95%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="#1c2333" strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ fill: '#8b949e', fontFamily: 'Space Mono', fontSize: 10 }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tick={{ fill: '#8b949e', fontFamily: 'Space Mono', fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v) => `Rs ${(v / 1000).toFixed(0)}k`}
          width={48}
        />
        <Tooltip content={<CustomTooltip valuePrefix={valuePrefix} />} />
        <Area
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={2}
          fill={`url(#${gradientId})`}
          dot={false}
          activeDot={{ r: 4, fill: color, stroke: '#080c10', strokeWidth: 2 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

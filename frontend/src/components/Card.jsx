export default function Card({ children, className = '', glow = false }) {
  return (
    <div
      className={`
        bg-surface/95 border border-border/80 rounded-2xl p-5 md:p-6 shadow-sm shadow-black/20
        transition-all duration-200
        ${glow ? 'card-glow' : ''}
        ${className}
      `}
    >
      {children}
    </div>
  )
}

export function CardLabel({ children }) {
  return (
    <p className="font-mono text-[10px] text-muted tracking-widest uppercase mb-1">
      {children}
    </p>
  )
}

export function CardValue({ children, className = '' }) {
  return (
    <p className={`font-mono text-2xl font-bold text-white ${className}`}>
      {children}
    </p>
  )
}

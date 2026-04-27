export default function Card({ children, className = '', glow = false }) {
  return (
    <div
      className={`
        bg-surface border border-border rounded-xl p-5
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

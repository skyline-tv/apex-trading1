import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, Wallet, History, Settings, Zap,
} from 'lucide-react'

const links = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/wallet', label: 'Wallet', icon: Wallet },
  { to: '/history', label: 'History', icon: History },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export default function Navbar() {
  return (
    <>
      <header className="fixed inset-x-0 top-0 z-50 border-b border-border/80 bg-surface/90 backdrop-blur-md lg:hidden shadow-elevate">
        <div className="px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Zap size={16} className="text-accent" />
            <span className="font-sans font-800 text-base tracking-widest text-white uppercase">
              APEX
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse-slow" />
            <span className="font-mono text-[10px] text-muted tracking-widest">LIVE SIM</span>
          </div>
        </div>
      </header>

      <aside className="hidden fixed inset-y-0 left-0 z-40 h-screen w-56 border-r border-border/80 bg-surface/95 backdrop-blur-md lg:flex lg:flex-col shadow-elevate">
        <div className="px-6 py-6 border-b border-border">
          <div className="flex items-center gap-2">
            <Zap size={18} className="text-accent" />
            <span className="font-sans font-800 text-lg tracking-widest text-white uppercase">
              APEX
            </span>
          </div>
          <p className="font-mono text-[10px] text-muted mt-1 tracking-widest">
            AI PAPER TRADER
          </p>
        </div>

        <nav className="flex-1 flex flex-col space-y-1 px-3 py-4">
          {links.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-xl font-mono text-xs tracking-wider transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/35 focus-visible:ring-offset-2 focus-visible:ring-offset-surface ${
                  isActive
                    ? 'border border-accent/25 bg-accent/[0.08] text-accent shadow-sm shadow-black/20'
                    : 'border border-transparent text-muted hover:border-border hover:bg-border/40 hover:text-white'
                }`
              }
            >
              <Icon size={15} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-border px-6 py-4">
          <div className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse-slow" />
            <span className="font-mono text-[10px] text-muted tracking-widest">LIVE SIM</span>
          </div>
        </div>
      </aside>

      <nav className="fixed inset-x-0 bottom-0 z-50 border-t border-border/80 bg-surface/90 backdrop-blur-md lg:hidden pb-[env(safe-area-inset-bottom)] shadow-[0_-8px_32px_-8px_rgba(0,0,0,0.45)]">
        <div className="grid grid-cols-4 gap-1 px-2 py-2">
          {links.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex flex-col items-center justify-center gap-1 rounded-xl px-1 py-2 font-mono text-[10px] tracking-wide transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/35 focus-visible:ring-offset-2 focus-visible:ring-offset-surface ${
                  isActive
                    ? 'border border-accent/25 bg-accent/[0.08] text-accent'
                    : 'border border-transparent text-muted hover:bg-border/40 hover:text-white'
                }`
              }
            >
              <Icon size={14} />
              <span>{label}</span>
            </NavLink>
          ))}
        </div>
      </nav>
    </>
  )
}

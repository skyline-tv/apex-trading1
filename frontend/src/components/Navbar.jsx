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
      <header className="fixed inset-x-0 top-0 z-50 border-b border-border bg-surface/95 backdrop-blur lg:hidden">
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

      <aside className="hidden fixed inset-y-0 left-0 z-40 h-screen w-56 border-r border-border bg-surface lg:flex lg:flex-col">
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
                `flex items-center gap-3 px-3 py-2.5 rounded-lg font-mono text-xs tracking-wider transition-all duration-150 ${
                  isActive
                    ? 'bg-accent/10 text-accent border border-accent/20'
                    : 'text-muted hover:text-white hover:bg-border/50'
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

      <nav className="fixed inset-x-0 bottom-0 z-50 border-t border-border bg-surface/95 backdrop-blur lg:hidden">
        <div className="grid grid-cols-4 gap-1 px-2 py-2">
          {links.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex flex-col items-center justify-center gap-1 rounded-lg px-1 py-1.5 font-mono text-[10px] tracking-wide transition ${
                  isActive
                    ? 'text-accent bg-accent/10 border border-accent/25'
                    : 'text-muted hover:text-white hover:bg-border/40'
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

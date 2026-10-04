import {
  BarChart3,
  Bell,
  Boxes,
  FileEdit,
  LayoutDashboard,
  LogOut,
  Menu,
  Monitor,
  Moon,
  Settings as SettingsIcon,
  ReceiptText,
  Sparkles,
  ShoppingCart,
  Sun,
  Users,
  X,
} from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import Avatar from './Avatar'
import BrandMark from './BrandMark'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'
import { useStoreSettings } from '../hooks/useStoreSettings'
import { api } from '../lib/api'

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/inventory', label: 'Inventory', icon: Boxes },
  { to: '/pos', label: 'Sales (POS)', icon: ShoppingCart },
  { to: '/sales-history', label: 'Sales History', icon: ReceiptText },
  { to: '/customers', label: 'Customers', icon: Users },
  { to: '/reports', label: 'Reports & Analytics', icon: BarChart3, ownerOnly: true },
  { to: '/ipf', label: 'Items Prices in Future (IPF)', icon: Sparkles, ownerOnly: true },
  { to: '/details-input', label: 'Details Input (Owner)', icon: FileEdit, ownerOnly: true },
  { to: '/settings', label: 'Settings', icon: SettingsIcon },
]

const PAGE_TITLES = {
  '/': 'Store Operations Dashboard',
  '/inventory': 'Inventory Management',
  '/pos': 'Sales (POS)',
  '/sales-history': 'Sales History',
  '/customers': 'Customers',
  '/reports': 'Reports & Analytics',
  '/ipf': 'Items Prices in Future (IPF)',
  '/details-input': 'Details Input (Owner)',
  '/settings': 'Settings',
}

function RestockBell() {
  const { data } = useQuery({
    queryKey: ['dashboard', 'metrics'],
    queryFn: () => api('/api/dashboard/metrics'),
    refetchInterval: 60_000,
  })
  const alerts = (data?.low_stock_count ?? 0) + (data?.out_of_stock_count ?? 0)

  return (
    <NavLink
      to="/inventory?status=LOW_STOCK"
      className="relative rounded-lg p-2 text-ink-muted transition hover:bg-surface-muted hover:text-ink"
      title={alerts ? `${alerts} product(s) need restocking` : 'No restock alerts'}
      aria-label={alerts ? `${alerts} products need restocking` : 'No restock alerts'}
    >
      <Bell className="h-5 w-5" />
      {alerts > 0 ? (
        <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-semibold text-white">
          {alerts > 9 ? '9+' : alerts}
        </span>
      ) : null}
    </NavLink>
  )
}

const THEME_ORDER = ['light', 'dark', 'system']
const THEME_ICONS = { light: Sun, dark: Moon, system: Monitor }
const THEME_LABELS = { light: 'Light theme', dark: 'Dark theme', system: 'Match system theme' }

function ThemeToggle() {
  const { preference, choose } = useTheme()
  const Icon = THEME_ICONS[preference] ?? Monitor
  const next = THEME_ORDER[(THEME_ORDER.indexOf(preference) + 1) % THEME_ORDER.length]

  return (
    <button
      type="button"
      onClick={() => choose(next)}
      className="rounded-lg p-2 text-ink-muted transition hover:bg-surface-muted hover:text-ink"
      title={`${THEME_LABELS[preference]} — switch to ${THEME_LABELS[next].toLowerCase()}`}
      aria-label={`${THEME_LABELS[preference]}. Switch to ${THEME_LABELS[next].toLowerCase()}`}
    >
      <Icon className="h-5 w-5" />
    </button>
  )
}

function SidebarContent({ onNavigate }) {
  const { user, isOwner, logout } = useAuth()
  const { data: store } = useStoreSettings()
  const visibleItems = NAV_ITEMS.filter((item) => !item.ownerOnly || isOwner)

  return (
    <div className="flex h-full flex-col bg-sidebar text-slate-300">
      <div className="flex items-center gap-3 px-5 py-6">
        <BrandMark className="h-9 w-9 shrink-0" />
        <span className="text-sm font-semibold uppercase leading-tight tracking-wide text-white">
          {store?.name || 'Super Sale'}
        </span>
      </div>

      <nav className="flex-1 space-y-1 px-3 scroll-slim overflow-y-auto" aria-label="Main">
        {visibleItems.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={onNavigate}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition
               ${isActive ? 'bg-sidebar-active text-white' : 'text-slate-400 hover:bg-white/5 hover:text-white'}`
            }
          >
            <Icon className="h-[18px] w-[18px] shrink-0" aria-hidden="true" />
            <span className="truncate">{label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-white/10 px-3 py-4">
        <div className="mb-2 flex items-center gap-3 px-3">
          <Avatar user={user} className="h-8 w-8" textClassName="text-xs" />
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-white">{user?.full_name}</p>
            <p className="text-xs uppercase tracking-wide text-slate-400">{user?.role}</p>
          </div>
        </div>
        <button
          type="button"
          onClick={logout}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-400 transition hover:bg-white/5 hover:text-white"
        >
          <LogOut className="h-[18px] w-[18px]" aria-hidden="true" />
          Sign out
        </button>
      </div>
    </div>
  )
}

export default function Layout() {
  const location = useLocation()
  const { user } = useAuth()
  const [mobileOpen, setMobileOpen] = useState(false)
  const title = PAGE_TITLES[location.pathname] ?? 'Super Sale'

  return (
    <div className="flex h-full">
      <aside className="hidden w-64 shrink-0 lg:block">
        <SidebarContent />
      </aside>

      {mobileOpen ? (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/50" onClick={() => setMobileOpen(false)} role="presentation" />
          <div className="relative h-full w-64">
            <SidebarContent onNavigate={() => setMobileOpen(false)} />
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              className="absolute -right-10 top-4 rounded-lg bg-white/10 p-2 text-white"
              aria-label="Close menu"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-4 border-b border-edge bg-surface px-4 py-4 sm:px-6">
          <button
            type="button"
            className="rounded-lg p-2 text-ink-muted hover:bg-surface-muted lg:hidden"
            onClick={() => setMobileOpen(true)}
            aria-label="Open menu"
          >
            <Menu className="h-5 w-5" />
          </button>
          <h1 className="truncate text-xl font-semibold text-ink sm:text-2xl">{title}</h1>
          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            <ThemeToggle />
            <RestockBell />
            <div className="hidden text-right sm:block">
              <p className="text-sm font-medium text-ink">{user?.full_name}</p>
              <p className="text-xs text-ink-faint">{user?.role === 'OWNER' ? 'Owner' : 'Cashier'}</p>
            </div>
            <Avatar user={user} />
          </div>
        </header>

        <main className="flex-1 overflow-y-auto scroll-slim bg-app p-4 sm:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

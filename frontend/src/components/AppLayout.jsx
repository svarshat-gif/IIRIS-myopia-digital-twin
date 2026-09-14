/** Shell for every signed-in page: sidebar on desktop, bottom bar on mobile. */
import React, { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { api } from '../lib/api'
import Logo from './Logo'

const NAV = [
  { to: '/app', end: true, label: 'Home', icon: IconHome },
  { to: '/app/records', label: 'My records', icon: IconRecords },
  { to: '/app/appointments', label: 'Appointments', icon: IconCalendar },
  { to: '/app/simulator', label: 'Simulator', icon: IconSpark },
  { to: '/app/insights', label: 'Insights', icon: IconInsight },
  { to: '/app/profile', label: 'Profile', icon: IconUser },
]

function initials(name = '') {
  return name.trim().split(/\s+/).slice(0, 2).map((w) => w[0]?.toUpperCase()).join('')
}

export default function AppLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [synthetic, setSynthetic] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    api.health().then((h) => setSynthetic(!!h.data_is_synthetic)).catch(() => {})
  }, [])
  useEffect(() => { setMenuOpen(false) }, [location.pathname])

  return (
    <div className="relative min-h-screen">
      {/* Demo-data notice. Disappears on its own once a real model is loaded. */}
      {synthetic && (
        <div className="bg-ink px-4 py-2 text-center text-[12px] text-sand-200">
          Demo mode — the model behind these numbers is trained on{' '}
          <strong className="font-semibold text-sand-50">synthetic data</strong>, so
          treat everything here as an illustration, not eye-health advice.
        </div>
      )}

      <div className="mx-auto flex max-w-[1400px] gap-6 px-4 py-5 lg:px-6">
        {/* ---------------- sidebar (desktop) ---------------- */}
        <aside className="sticky top-5 hidden h-[calc(100vh-2.5rem)] w-60 shrink-0
                          flex-col lg:flex">
          <NavLink to="/app" className="mb-7 mt-1 inline-flex px-2 text-ink">
            <Logo />
          </NavLink>

          <nav className="flex flex-col gap-1">
            {NAV.map(({ to, end, label, icon: Icon }) => (
              <NavLink key={to} to={to} end={end}
                       className={({ isActive }) =>
                         `nav-link ${isActive ? 'nav-link-active' : ''}`}>
                <Icon />
                {label}
              </NavLink>
            ))}
          </nav>

          <div className="mt-auto">
            <div className="card-quiet p-3">
              <div className="flex items-center gap-2.5">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center
                                 rounded-full bg-ink text-[13px] font-semibold text-sand-50">
                  {initials(user?.full_name)}
                </span>
                <div className="min-w-0">
                  <div className="truncate text-[13px] font-medium">{user?.full_name}</div>
                  <div className="truncate text-[11px] text-ink-faint">{user?.email}</div>
                </div>
              </div>
              <button className="btn btn-ghost btn-sm mt-2 w-full"
                      onClick={() => { logout(); navigate('/') }}>
                Sign out
              </button>
            </div>
          </div>
        </aside>

        {/* ---------------- main ---------------- */}
        <div className="min-w-0 flex-1 pb-24 lg:pb-6">
          {/* mobile header */}
          <header className="mb-5 flex items-center justify-between lg:hidden">
            <NavLink to="/app" className="text-ink"><Logo size="sm" /></NavLink>
            <button onClick={() => setMenuOpen((o) => !o)}
                    aria-label="Account menu"
                    className="flex h-9 w-9 items-center justify-center rounded-full
                               bg-ink text-[12px] font-semibold text-sand-50">
              {initials(user?.full_name)}
            </button>
          </header>
          {menuOpen && (
            <div className="mb-4 animate-fade-in card p-3 lg:hidden">
              <div className="px-1 text-[13px] font-medium">{user?.full_name}</div>
              <div className="px-1 text-[11px] text-ink-faint">{user?.email}</div>
              <button className="btn btn-secondary btn-sm mt-3 w-full"
                      onClick={() => { logout(); navigate('/') }}>Sign out</button>
            </div>
          )}

          {/* Keying on the path replays the entrance animation on every navigation. */}
          <div key={location.pathname} className="page-enter">
            <Outlet />
          </div>
        </div>
      </div>

      {/* ---------------- bottom bar (mobile) ---------------- */}
      <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-sand-100/95
                      backdrop-blur lg:hidden">
        <div className="mx-auto flex max-w-lg justify-between px-2 py-1.5">
          {NAV.map(({ to, end, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={end}
                     className={({ isActive }) =>
                       `flex flex-1 flex-col items-center gap-1 rounded-lg px-1 py-2
                        text-[10px] font-medium transition-colors ${
                         isActive ? 'text-ink' : 'text-ink-faint'}`}>
              <Icon />
              <span className="truncate">{label.split(' ')[0]}</span>
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  )
}

/* ------------------------------------------------------------------- icons */
const s = { width: 18, height: 18, viewBox: '0 0 20 20', fill: 'none',
            stroke: 'currentColor', strokeWidth: 1.6, strokeLinecap: 'round',
            strokeLinejoin: 'round', 'aria-hidden': true }

function IconHome() {
  return <svg {...s}><path d="M3 8.5 10 3l7 5.5V16a1 1 0 0 1-1 1h-3v-5H7v5H4a1 1 0 0 1-1-1z"/></svg>
}
function IconRecords() {
  return <svg {...s}><rect x="4" y="2.5" width="12" height="15" rx="2"/><path d="M7.5 7h5M7.5 10h5M7.5 13h3"/></svg>
}
function IconCalendar() {
  return <svg {...s}><rect x="3" y="4.5" width="14" height="13" rx="2"/><path d="M3 8.5h14M7 2.5v3M13 2.5v3"/></svg>
}
function IconSpark() {
  return <svg {...s}><path d="M10 2.5v3M10 14.5v3M2.5 10h3M14.5 10h3M5 5l2 2M13 13l2 2M15 5l-2 2M7 13l-2 2"/><circle cx="10" cy="10" r="2.4"/></svg>
}
function IconInsight() {
  return <svg {...s}><path d="M4 16V9M8.7 16V4M13.3 16v-5M18 16v-9"/></svg>
}
function IconUser() {
  return <svg {...s}><circle cx="10" cy="7" r="3.2"/><path d="M4 17c.9-3 3.2-4.5 6-4.5S15.1 14 16 17"/></svg>
}

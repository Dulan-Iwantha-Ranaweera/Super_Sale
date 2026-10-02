import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

const STORAGE_KEY = 'supersale.theme'
const ThemeContext = createContext(null)

/** 'light' | 'dark' | 'system' — system follows the operating system setting. */
function readStoredPreference() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    return stored === 'light' || stored === 'dark' || stored === 'system' ? stored : 'system'
  } catch {
    return 'system'
  }
}

function systemPrefersDark() {
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  } catch {
    return false
  }
}

export function ThemeProvider({ children }) {
  const [preference, setPreference] = useState(readStoredPreference)
  const [systemDark, setSystemDark] = useState(systemPrefersDark)

  // Follow the OS while the preference is 'system'.
  useEffect(() => {
    let media
    try {
      media = window.matchMedia('(prefers-color-scheme: dark)')
    } catch {
      return undefined
    }
    const onChange = (event) => setSystemDark(event.matches)
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [])

  const resolved = preference === 'system' ? (systemDark ? 'dark' : 'light') : preference

  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle('dark', resolved === 'dark')
    root.dataset.theme = resolved
    // Keep the browser chrome (address bar, form controls) in step.
    const meta = document.querySelector('meta[name="theme-color"]')
    if (meta) meta.setAttribute('content', resolved === 'dark' ? '#020617' : '#0f172a')
  }, [resolved])

  const choose = useCallback((next) => {
    setPreference(next)
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* private mode: the choice simply lasts for this tab */
    }
  }, [])

  const toggle = useCallback(() => {
    choose(resolved === 'dark' ? 'light' : 'dark')
  }, [choose, resolved])

  const value = useMemo(
    () => ({ preference, resolved, isDark: resolved === 'dark', choose, toggle }),
    [preference, resolved, choose, toggle],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) throw new Error('useTheme must be used inside a ThemeProvider')
  return context
}

/** Chart colours that follow the theme — Recharts needs real values, not classes. */
export function useChartTheme() {
  const { isDark } = useTheme()
  return useMemo(
    () => ({
      grid: isDark ? '#1e293b' : '#e2e8f0',
      axis: isDark ? '#94a3b8' : '#64748b',
      tooltip: {
        borderRadius: 8,
        border: `1px solid ${isDark ? '#334155' : '#e2e8f0'}`,
        backgroundColor: isDark ? '#0f172a' : '#ffffff',
        color: isDark ? '#e2e8f0' : '#1e293b',
        fontSize: 12,
      },
      cursor: isDark ? 'rgba(148,163,184,0.18)' : 'rgba(148,163,184,0.12)',
      series: {
        blue: isDark ? '#60a5fa' : '#3b82f6',
        green: isDark ? '#34d399' : '#10b981',
        red: isDark ? '#fb7185' : '#f43f5e',
      },
    }),
    [isDark],
  )
}

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, clearSession, getStoredUser, getToken, saveSession } from '../lib/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => (getToken() ? getStoredUser() : null))
  const [checking, setChecking] = useState(() => Boolean(getToken()))

  // Revalidate a stored token on boot so an expired session never renders a
  // half-working dashboard.
  useEffect(() => {
    let cancelled = false
    if (!getToken()) {
      setChecking(false)
      return undefined
    }
    api('/api/auth/me')
      .then((profile) => {
        if (!cancelled) setUser(profile)
      })
      .catch(() => {
        if (!cancelled) {
          clearSession()
          setUser(null)
        }
      })
      .finally(() => {
        if (!cancelled) setChecking(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    const handleUnauthorized = () => setUser(null)
    window.addEventListener('supersale:unauthorized', handleUnauthorized)
    return () => window.removeEventListener('supersale:unauthorized', handleUnauthorized)
  }, [])

  const login = useCallback(async (username, password) => {
    const result = await api('/api/auth/login', {
      method: 'POST',
      body: { username, password },
    })
    saveSession(result.access_token, result.user)
    setUser(result.user)
    return result.user
  }, [])

  /** Re-read the profile after an edit so the sidebar and topbar update. */
  const refreshUser = useCallback(async () => {
    const profile = await api('/api/auth/me')
    setUser(profile)
    return profile
  }, [])

  const logout = useCallback(() => {
    clearSession()
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({ user, checking, login, logout, refreshUser, isOwner: user?.role === 'OWNER' }),
    [user, checking, login, logout, refreshUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside an AuthProvider')
  return context
}

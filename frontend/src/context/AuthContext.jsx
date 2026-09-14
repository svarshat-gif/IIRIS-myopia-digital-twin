import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, setUnauthorizedHandler, token } from '../lib/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)

  // Restore the session on first load, if the stored token is still valid.
  useEffect(() => {
    let alive = true
    if (!token.get()) { setReady(true); return }
    api.me()
      .then((u) => alive && setUser(u))
      .catch(() => { token.set(null); alive && setUser(null) })
      .finally(() => alive && setReady(true))
    return () => { alive = false }
  }, [])

  // A 401 anywhere signs the user out, so the UI can never sit in a
  // half-authenticated state showing stale data.
  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null))
    return () => setUnauthorizedHandler(null)
  }, [])

  const login = useCallback(async (email, password) => {
    const res = await api.login({ email, password })
    token.set(res.access_token)
    setUser(res.user)
    return res.user
  }, [])

  const signup = useCallback(async (payload) => {
    const res = await api.signup(payload)
    token.set(res.access_token)
    setUser(res.user)
    return res.user
  }, [])

  const logout = useCallback(() => { token.set(null); setUser(null) }, [])

  const refresh = useCallback(async () => {
    try { setUser(await api.me()) } catch { /* handled by the 401 hook */ }
  }, [])

  const value = useMemo(
    () => ({ user, ready, login, signup, logout, refresh, setUser }),
    [user, ready, login, signup, logout, refresh])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}

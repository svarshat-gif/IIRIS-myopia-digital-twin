import React, { useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import './lib/charts'
import { installRipple } from './lib/interactions'
import { AuthProvider, useAuth } from './context/AuthContext'
import { Spinner, ToastProvider } from './components/ui'
import AppLayout from './components/AppLayout'
import Landing from './pages/Landing'
import { Login, Signup } from './pages/Auth'
import Dashboard from './pages/Dashboard'
import Records from './pages/Records'
import Appointments from './pages/Appointments'
import Simulator from './pages/Simulator'
import PublicSimulator from './pages/PublicSimulator'
import Insights from './pages/Insights'
import Profile from './pages/Profile'

/** Sends signed-out visitors to sign-in, remembering where they were going. */
function RequireAuth({ children }) {
  const { user, ready } = useAuth()
  const location = useLocation()
  if (!ready) return <div className="grid min-h-screen place-items-center">
    <Spinner label="Opening Iiris" /></div>
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return children
}

/** Someone already signed in has no use for the landing or auth pages. */
function RedirectIfAuthed({ children }) {
  const { user, ready } = useAuth()
  if (!ready) return <div className="grid min-h-screen place-items-center">
    <Spinner label="Opening Iiris" /></div>
  return user ? <Navigate to="/app" replace /> : children
}

export default function App() {
  useEffect(installRipple, [])
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <Routes>
            <Route path="/" element={<RedirectIfAuthed><Landing /></RedirectIfAuthed>} />
            <Route path="/login" element={<RedirectIfAuthed><Login /></RedirectIfAuthed>} />
            <Route path="/signup" element={<RedirectIfAuthed><Signup /></RedirectIfAuthed>} />
            <Route path="/try" element={<PublicSimulator />} />

            <Route path="/app" element={<RequireAuth><AppLayout /></RequireAuth>}>
              <Route index element={<Dashboard />} />
              <Route path="records" element={<Records />} />
              <Route path="appointments" element={<Appointments />} />
              <Route path="simulator" element={<Simulator />} />
              <Route path="insights" element={<Insights />} />
              <Route path="profile" element={<Profile />} />
            </Route>

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}

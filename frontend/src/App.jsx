import React, { useEffect, lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { installRipple } from './lib/interactions'
import { AuthProvider, useAuth } from './context/AuthContext'
import { Spinner, ToastProvider } from './components/ui'
import AppLayout from './components/AppLayout'
const Landing = lazy(() => import('./pages/Landing'))
const Login = lazy(() => import('./pages/Auth').then(m => ({ default: m.Login })))
const Signup = lazy(() => import('./pages/Auth').then(m => ({ default: m.Signup })))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Records = lazy(() => import('./pages/Records'))
const Appointments = lazy(() => import('./pages/Appointments'))
const Simulator = lazy(() => import('./pages/Simulator'))
const PublicSimulator = lazy(() => import('./pages/PublicSimulator'))
const Insights = lazy(() => import('./pages/Insights'))
const Profile = lazy(() => import('./pages/Profile'))

const ModelCard = lazy(() => import('./pages/ModelCard'))
const Cohort = lazy(() => import('./pages/Clinician').then(m => ({ default: m.Cohort })))
const PatientDetail = lazy(() => import('./pages/Clinician').then(m => ({ default: m.PatientDetail })))
export function RequireRole({ children }) {
  const { user } = useAuth()
  return ['clinician', 'admin'].includes(user?.role) ? children : <Navigate to="/app" replace />
}
function Home() {
  const { user } = useAuth()
  return ['clinician', 'admin'].includes(user?.role) ? <Navigate to="cohort" replace /> : <Dashboard />
}

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
          <Suspense fallback={<Spinner label="Opening page" />}><Routes>
            <Route path="/" element={<RedirectIfAuthed><Landing /></RedirectIfAuthed>} />
            <Route path="/login" element={<RedirectIfAuthed><Login /></RedirectIfAuthed>} />
            <Route path="/signup" element={<RedirectIfAuthed><Signup /></RedirectIfAuthed>} />
            <Route path="/try" element={<PublicSimulator />} />

            <Route path="/app" element={<RequireAuth><AppLayout /></RequireAuth>}>
              <Route index element={<Home />} />
              <Route path="cohort" element={<RequireRole><Cohort /></RequireRole>} />
              <Route path="cohort/:patientId" element={<RequireRole><PatientDetail /></RequireRole>} />
              <Route path="model" element={<ModelCard />} />
              <Route path="records" element={<Records />} />
              <Route path="appointments" element={<Appointments />} />
              <Route path="simulator" element={<Simulator />} />
              <Route path="insights" element={<Insights />} />
              <Route path="profile" element={<Profile />} />
            </Route>

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes></Suspense>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}

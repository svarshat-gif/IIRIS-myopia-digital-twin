import Logo from '../components/Logo'
/** Sign in and sign up share a layout, so the two feel like one flow. */
import React, { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import {ErrorNote, Field} from '../components/ui'

const DEMO = { email: 'demo@iiris.health', password: 'irisdemo2026' }

function Shell({ title, kicker, children, footer }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[1fr_1.1fr]">
      <div className="flex flex-col justify-center px-6 py-10 sm:px-12">
        <div className="mx-auto w-full max-w-sm">
          <Link to="/" className="mb-10 inline-flex text-ink"><Logo /></Link>
          <p className="script text-2xl text-ink-muted">{kicker}</p>
          <h1 className="mt-1 text-3xl font-semibold">{title}</h1>
          <div className="mt-8">{children}</div>
          <div className="mt-6 text-[13.5px] text-ink-muted">{footer}</div>
        </div>
      </div>

      {/* Quiet supporting panel — no imagery, just the promise restated. */}
      <div className="grain relative hidden overflow-hidden bg-ink lg:block">
        <div className="relative z-10 flex h-full flex-col justify-center px-14
                        text-sand-100">
          <p className="script text-3xl text-sand-500">one place</p>
          <h2 className="mt-3 max-w-md text-4xl font-semibold leading-tight text-sand-50">
            Every reading you have ever had, and where it is heading.
          </h2>
          <ul className="mt-10 space-y-4 text-[15px] text-sand-300">
            {['Your full prescription history, kept together',
              'A projection that shows its own uncertainty',
              'What-if scenarios for habits you can actually change',
              'Past and upcoming appointments in one list'].map((t) => (
              <li key={t} className="flex items-start gap-3">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-sand-500" />
                {t}
              </li>
            ))}
          </ul>
          <p className="mt-12 max-w-sm text-[12px] leading-relaxed text-sand-600">
            Iiris supports conversations with your optometrist. It does not diagnose or
            replace one.
          </p>
        </div>
      </div>
    </div>
  )
}

export function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [form, setForm] = useState({ email: '', password: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const target = location.state?.from || '/app'

  async function submit(e, creds) {
    e?.preventDefault()
    setBusy(true); setError(null)
    try {
      const c = creds || form
      await login(c.email, c.password)
      navigate(target, { replace: true })
    } catch (err) { setError(err) } finally { setBusy(false) }
  }

  return (
    <Shell kicker="welcome back" title="Sign in to Iiris"
           footer={<>New here? <Link to="/signup"
             className="font-medium text-ink underline underline-offset-2">
             Create an account</Link>.</>}>
      <form onSubmit={submit} className="space-y-4">
        <Field label="Email">
          <input className="input" type="email" autoComplete="email" required
                 value={form.email} placeholder="you@example.com"
                 onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </Field>
        <Field label="Password">
          <input className="input" type="password" autoComplete="current-password"
                 required value={form.password} placeholder="••••••••"
                 onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </Field>

        <ErrorNote error={error} />

        <button className="btn-primary w-full" disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>

      <div className="mt-6 rounded-xl border border-dashed border-line-strong
                      bg-sand-50 p-4">
        <p className="text-[13px] font-medium">Just looking around?</p>
        <p className="mt-1 text-[12.5px] leading-relaxed text-ink-muted">
          The demo account has four years of history already in it.
        </p>
        <button type="button" disabled={busy}
                onClick={(e) => { setForm(DEMO); submit(e, DEMO) }}
                className="btn btn-secondary btn-sm mt-3 w-full">
          Open the demo account
        </button>
      </div>
    </Shell>
  )
}

export function Signup() {
  const { signup } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({
    full_name: '', email: '', password: '',
    age: '', sex: '', parental_myopia: '',
  })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const weak = form.password.length > 0 && form.password.length < 8

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      await signup({
        full_name: form.full_name.trim(),
        email: form.email.trim(),
        password: form.password,
        age: form.age === '' ? null : Number(form.age),
        sex: form.sex || null,
        parental_myopia: form.parental_myopia === '' ? null
          : Number(form.parental_myopia),
      })
      navigate('/app', { replace: true })
    } catch (err) { setError(err) } finally { setBusy(false) }
  }

  return (
    <Shell kicker="nice to meet you" title="Create your Iiris account"
           footer={<>Already have one? <Link to="/login"
             className="font-medium text-ink underline underline-offset-2">
             Sign in</Link>.</>}>
      <form onSubmit={submit} className="space-y-4">
        <Field label="Your name" required>
          <input className="input" autoComplete="name" required value={form.full_name}
                 placeholder="Riya Sharma"
                 onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
        </Field>
        <Field label="Email" required>
          <input className="input" type="email" autoComplete="email" required
                 value={form.email} placeholder="you@example.com"
                 onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </Field>
        <Field label="Password" required
               error={weak ? 'Use at least 8 characters.' : null}
               hint="At least 8 characters.">
          <input className={`input ${weak ? 'input-error' : ''}`} type="password"
                 autoComplete="new-password" required minLength={8}
                 value={form.password} placeholder="••••••••"
                 onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </Field>

        <div className="rounded-xl border border-line bg-sand-50 p-4">
          <p className="text-[13px] font-medium">A little about your eyes</p>
          <p className="mt-0.5 text-[12px] text-ink-muted">
            Optional, and you can change it later. It helps the model from day one.
          </p>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <Field label="Age">
              <input className="input" type="number" min="3" max="120" step="0.5"
                     value={form.age} placeholder="12"
                     onChange={(e) => setForm({ ...form, age: e.target.value })} />
            </Field>
            <Field label="Sex">
              <select className="input" value={form.sex}
                      onChange={(e) => setForm({ ...form, sex: e.target.value })}>
                <option value="">Prefer not to say</option>
                <option value="female">Female</option>
                <option value="male">Male</option>
                <option value="other">Other</option>
              </select>
            </Field>
            <div className="col-span-2">
              <Field label="Short-sighted parents"
                     hint="Family history is one of the strongest signals there is.">
                <select className="input" value={form.parental_myopia}
                        onChange={(e) => setForm({ ...form,
                                                   parental_myopia: e.target.value })}>
                  <option value="">Not sure</option>
                  <option value="0">Neither</option>
                  <option value="1">One</option>
                  <option value="2">Both</option>
                </select>
              </Field>
            </div>
          </div>
        </div>

        <ErrorNote error={error} />

        <button className="btn-primary w-full" disabled={busy || weak}>
          {busy ? 'Creating your account…' : 'Create account'}
        </button>
        <p className="text-[11.5px] leading-relaxed text-ink-faint">
          Iiris stores what you enter so you can track it over time. It is a
          decision-support tool, not a medical device, and it does not diagnose.
        </p>
      </form>
    </Shell>
  )
}

import React, { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { api, fmt } from '../lib/api'
import {
  Card, Collapsible, ErrorNote, Field, NumberField, StatusChip, useToast,
} from '../components/ui'

export default function Profile() {
  const { user, refresh, logout } = useAuth()
  const toast = useToast()
  const [twin, setTwin] = useState(null)
  const [form, setForm] = useState({ full_name: '', age: null, sex: '',
                                     parental_myopia: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [pw, setPw] = useState({ current_password: '', new_password: '' })
  const [pwBusy, setPwBusy] = useState(false)
  const [pwError, setPwError] = useState(null)

  useEffect(() => {
    api.twin().then(setTwin).catch(() => setTwin(null))
  }, [])

  useEffect(() => {
    if (!user) return
    setForm((f) => ({ ...f, full_name: user.full_name || '' }))
  }, [user])

  useEffect(() => {
    if (!twin) return
    setForm((f) => ({
      ...f,
      age: twin.patient.age_at_start ?? null,
      sex: twin.patient.sex || '',
      parental_myopia: twin.patient.parental_myopia ?? '',
    }))
  }, [twin])

  async function save(e) {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      await api.updateProfile({
        full_name: form.full_name,
        age: form.age,
        sex: form.sex || null,
        parental_myopia: form.parental_myopia === '' ? null
          : Number(form.parental_myopia),
      })
      await refresh()
      toast('Profile saved')
    } catch (err) { setError(err) } finally { setBusy(false) }
  }

  async function changePassword(e) {
    e.preventDefault()
    setPwBusy(true); setPwError(null)
    try {
      await api.changePassword(pw)
      setPw({ current_password: '', new_password: '' })
      toast('Password changed')
    } catch (err) { setPwError(err) } finally { setPwBusy(false) }
  }

  async function downloadRecord() {
    try {
      const bundle = await api.fhir()
      const blob = new Blob([JSON.stringify(bundle, null, 2)],
                            { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `iiris-record-${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
      toast('Record downloaded')
    } catch (err) { setError(err) }
  }

  return (
    <div className="space-y-5">
      <div>
        <p className="script text-2xl text-ink-muted">your details</p>
        <h1 className="text-3xl font-semibold">Profile</h1>
      </div>

      <Card title="About you"
            subtitle="Age and family history feed the model, so keeping them current matters.">
        <form onSubmit={save} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Name">
              <input className="input" value={form.full_name}
                     onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
            </Field>
            <NumberField label="Age" unit="yrs" step="0.5" value={form.age}
                         onChange={(v) => setForm({ ...form, age: v })} />
            <Field label="Sex">
              <select className="input" value={form.sex}
                      onChange={(e) => setForm({ ...form, sex: e.target.value })}>
                <option value="">Prefer not to say</option>
                <option value="female">Female</option>
                <option value="male">Male</option>
                <option value="other">Other</option>
              </select>
            </Field>
            <Field label="Short-sighted parents">
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
          <ErrorNote error={error} />
          <button className="btn-primary" disabled={busy}>
            {busy ? 'Saving…' : 'Save changes'}
          </button>
        </form>
      </Card>

      <Card title="Your account">
        <dl className="grid gap-x-8 gap-y-2.5 text-[13.5px] sm:grid-cols-2">
          {[['Email', user?.email],
            ['Member since', fmt.date(user?.created_at?.slice(0, 10))],
            ['Results saved', user?.n_visits ?? 0],
            ['Record version', `v${user?.twin_version ?? 0}`]].map(([k, v]) => (
            <div key={k} className="flex items-baseline justify-between gap-3
                                    border-b border-line/70 pb-2">
              <dt className="text-ink-muted">{k}</dt>
              <dd className="font-medium">{v}</dd>
            </div>
          ))}
        </dl>

        <div className="mt-5 flex flex-wrap gap-2">
          <button className="btn-secondary btn-sm" onClick={downloadRecord}>
            Download my record
          </button>
          <button className="btn btn-ghost btn-sm" onClick={logout}>Sign out</button>
        </div>
        <p className="mt-3 text-[12px] leading-relaxed text-ink-faint">
          Your record downloads as an HL7 FHIR bundle — a standard health-data format,
          so another system can read it. Model estimates inside it are clearly marked as
          estimates, never as measurements.
        </p>
      </Card>

      <Card title="Password">
        <form onSubmit={changePassword} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Current password">
              <input className="input" type="password" required
                     autoComplete="current-password" value={pw.current_password}
                     onChange={(e) => setPw({ ...pw,
                                              current_password: e.target.value })} />
            </Field>
            <Field label="New password" hint="At least 8 characters.">
              <input className="input" type="password" required minLength={8}
                     autoComplete="new-password" value={pw.new_password}
                     onChange={(e) => setPw({ ...pw, new_password: e.target.value })} />
            </Field>
          </div>
          <ErrorNote error={pwError} />
          <button className="btn-secondary" disabled={pwBusy}>
            {pwBusy ? 'Updating…' : 'Change password'}
          </button>
        </form>
      </Card>

      <Card title="What Iiris is, and is not">
        <ul className="space-y-2.5 text-[13.5px] leading-relaxed text-ink-muted">
          {['Iiris is a decision-support tool. It does not diagnose and it does not prescribe.',
            'Projections are model estimates. They show what the model expects, not what will happen.',
            'A what-if scenario shows how the estimate moves when an input changes. It is not evidence that the habit causes the change.',
            'Habit and screen-setup values you enter are self-reported, not clinical measurements.',
            'Always speak to a qualified optometrist or ophthalmologist about your eyes.'].map((t) => (
            <li key={t} className="flex gap-2.5">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-sand-500" />
              {t}
            </li>
          ))}
        </ul>
        <Collapsible label="About the model behind the numbers">
          <ModelNote />
        </Collapsible>
      </Card>
    </div>
  )
}

function ModelNote() {
  const [card, setCard] = useState(null)
  useEffect(() => { api.modelCard().then(setCard).catch(() => {}) }, [])
  if (!card) return <p className="text-[12.5px] text-ink-muted">Loading…</p>
  return (
    <div className="space-y-3 text-[12.5px] leading-relaxed text-ink-muted">
      {card.data_is_synthetic && (
        <div className="note-watch">
          This model was trained on <strong>synthetic data</strong> generated for
          development. Its numbers demonstrate how Iiris works; they carry no clinical
          meaning.
        </div>
      )}
      <p>
        Version <code className="rounded bg-sand-200 px-1.5 py-0.5">
          {card.model_version}</code>, {card.algorithm}. Predictions come with a{' '}
        {Math.round(card.interval_coverage * 100)}% range that is calibrated against
        people the model never saw during training.
      </p>
      <ul className="space-y-1.5">
        {card.limitations.slice(0, 4).map((l, i) => (
          <li key={i} className="flex gap-2">
            <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-sand-500" />{l}
          </li>
        ))}
      </ul>
    </div>
  )
}

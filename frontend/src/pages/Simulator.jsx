/** Read-only forecasts from a personal record or measured values entered by hand. */
import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { Card, Disclaimer, ErrorNote, Field, NumberField, Spinner } from '../components/ui'
import { checkForm, hasErrors } from '../lib/validate'
import ForecastPanel from '../components/ForecastPanel'

export default function Simulator({ publicMode = false }) {
  const [mode, setMode] = useState(publicMode ? 'quick' : 'mine')
  const [hasRecord, setHasRecord] = useState(!publicMode)
  useEffect(() => {
    if (publicMode) return
    let alive = true
    api.summary().then((summary) => {
      if (!alive) return
      setHasRecord(summary.has_record)
      if (!summary.has_record) setMode('quick')
    }).catch(() => {})
    return () => { alive = false }
  }, [publicMode])

  return <div className="space-y-5">
    <div>
      <p className="script text-2xl text-ink-muted">what could happen next</p>
      <h1 className="text-3xl font-semibold">Simulator</h1>
      <p className="lede mt-2 max-w-2xl text-[15px]">
        Explore spherical equivalent and axial length from one month to ten years ahead.
        Forecasts show estimated ranges and identify interpolation or extrapolation beyond measured follow-up.
      </p>
    </div>
    {!publicMode && <div className="flex w-fit gap-0.5 rounded-full border border-line-strong bg-white p-0.5">
      {[['mine', 'Use my record'], ['quick', 'Enter values by hand']].map(([key, label]) => <button key={key}
        onClick={() => setMode(key)} disabled={key === 'mine' && !hasRecord}
        className={`rounded-full px-4 py-2 text-[13px] font-medium transition-colors disabled:opacity-40 ${mode === key ? 'bg-ink text-sand-50' : 'text-ink-muted hover:text-ink'}`}>
        {label}
      </button>)}
    </div>}
    {mode === 'mine' ? <MyProjection /> : <QuickProjection publicMode={publicMode} />}
  </div>
}

function MyProjection() {
  const [twin, setTwin] = useState(null)
  const [error, setError] = useState(null)
  const loadForecast = useCallback((months, options) => api.prediction(months, options), [])
  useEffect(() => {
    let alive = true
    api.twin().then((value) => { if (alive) setTwin(value) }).catch((err) => { if (alive) setError(err) })
    return () => { alive = false }
  }, [])
  if (error) return <ErrorNote error={error} />
  if (!twin) return <Spinner label="Loading your record" />
  return <Card title="Forecast from my latest observation" subtitle="Choose any whole number of months, or its equivalent in years.">
    <ForecastPanel history={twin.history} loadPrediction={loadForecast} recordKey={`simulator:me:${twin.version}`} />
    <Disclaimer text={twin.disclaimer} />
  </Card>
}

const QUICK_BLANK = { age: null, spherical_equivalent: null, axial_length: null,
  parental_myopia: null, sex: '', treatment: '' }

function QuickProjection({ publicMode }) {
  const [form, setForm] = useState(QUICK_BLANK)
  const [submitted, setSubmitted] = useState(null)
  const { sex, treatment, ...numericForm } = form
  const fieldErrors = checkForm(numericForm, ['age', 'spherical_equivalent'])
  if (form.age !== null && form.age < 3) fieldErrors.age = 'Age must be at least 3 years.'
  const invalid = hasErrors(fieldErrors)
  const ready = form.age !== null && form.spherical_equivalent !== null
  const set = (name) => (value) => {
    setForm((current) => ({ ...current, [name]: value }))
    setSubmitted(null)
  }
  function submit(event) {
    event.preventDefault()
    if (invalid) return
    const values = Object.fromEntries(Object.entries(form).filter(([, value]) => value !== null && value !== ''))
    setSubmitted({ values, key: JSON.stringify(values) })
  }
  const loadForecast = useCallback((months, options) => api.quickForecast({ ...submitted.values, horizon_months: months }, options), [submitted])
  const history = useMemo(() => submitted ? [{ followup_month: 0,
    spherical_equivalent: submitted.values.spherical_equivalent,
    axial_length: submitted.values.axial_length ?? null }] : [], [submitted])

  return <div className="space-y-4">
    <Card title="Tell Iiris what you know" subtitle="Enter measured values only. Missing axial length stays unknown; forecasts remain exploratory.">
      <form onSubmit={submit} className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <NumberField name="age" label="Age" unit="yrs" min={3} step="0.5" required
            value={form.age} onChange={set('age')} />
          <NumberField name="spherical_equivalent" label="Prescription" unit="D" step="0.25" required
            value={form.spherical_equivalent} onChange={set('spherical_equivalent')} hint="Negative for short-sighted, e.g. −1.50" />
          <NumberField name="axial_length" label="Eye length" unit="mm" step="0.01"
            value={form.axial_length} onChange={set('axial_length')} hint="Optional, from a biometry scan. Usually 20–30 mm." />
          <Field label="Short-sighted parents" hint="Leave blank when unknown.">
            <select className="input" value={form.parental_myopia ?? ''} onChange={(event) => set('parental_myopia')(event.target.value === '' ? null : Number(event.target.value))}>
              <option value="">Not sure</option><option value="0">Neither</option><option value="1">One</option><option value="2">Both</option>
            </select>
          </Field>
          <Field label="Sex" hint="Optional, as recorded in the clinical record.">
            <select className="input" value={form.sex} onChange={(event) => set('sex')(event.target.value)}>
              <option value="">Not recorded</option><option value="female">Female</option><option value="male">Male</option><option value="other">Other</option><option value="unknown">Unknown</option>
            </select>
          </Field>
          <Field label="Current treatment" hint="Enter the treatment actually in use.">
            <select className="input" value={form.treatment} onChange={(event) => set('treatment')(event.target.value)}>
              <option value="">Not recorded</option><option value="none">No myopia-control treatment</option>
              <option value="atropine">Atropine</option><option value="ortho_k">Orthokeratology</option><option value="dims">DIMS lenses</option>
            </select>
          </Field>
        </div>
        <p className="text-xs text-ink-muted">Habit and ergonomic changes cannot be estimated from this model's training data.</p>
        {invalid && ready && <ul className="note-alert space-y-1">{Object.entries(fieldErrors).map(([name, message]) => <li key={name}>{message}</li>)}</ul>}
        <button type="submit" className="btn-primary btn-lg" disabled={!ready || invalid}>Show me the forecast</button>
      </form>
    </Card>
    {submitted && <>
      <Card title="Forecast from entered measurements" subtitle="Select any horizon from 1–120 months. Editing a measurement clears this forecast until you submit it again.">
        <ForecastPanel history={history} loadPrediction={loadForecast} recordKey={`quick:${submitted.key}`} />
        <Disclaimer text="Exploratory estimates, not a diagnosis. An estimated prediction range does not establish forecast accuracy at an unmeasured horizon." />
      </Card>
      {publicMode && <Card title="Keep this, and watch it change">
        <p className="lede text-sm">With an account, Iiris keeps the results you choose to add and shows the measured trend between them.</p>
        <Link to="/signup" className="btn-primary btn-sm mt-4">Create a free account</Link>
      </Card>}
    </>}
  </div>
}

/**
 * The simulator.
 *
 * Two modes:
 *   "mine"  — projects the signed-in user's own record forward, with an optional
 *             sustained habit change.
 *   "quick" — projects from values typed in by hand, for people with no record
 *             (and for the public /try page).
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, fmt } from '../lib/api'
import {
  Card, Collapsible, Disclaimer, ErrorNote, Field, NumberField, SliderField,
  Spinner, StatusChip, Tip, toneForCategory,
} from '../components/ui'
import { checkForm, hasErrors } from '../lib/validate'
import ProjectionChart from '../components/ProjectionChart'

const PRESETS = [
  { label: 'Two hours outdoors', changes: { outdoor_min: 120 },
    blurb: 'The single change with the most consistent support in the literature.' },
  { label: 'Less screen, further away',
    changes: { screen_time_hours: 2, viewing_distance_cm: 40 },
    blurb: 'Cut screen time and hold it at arm’s length.' },
  { label: 'Break every 20 minutes',
    changes: { continuous_session_min: 20, posture_score: 0.9 },
    blurb: 'Shorter unbroken sessions and a better set-up.' },
  { label: 'Everything at once',
    changes: { outdoor_min: 120, screen_time_hours: 2, viewing_distance_cm: 40,
               continuous_session_min: 20 },
    blurb: 'All of the above together.' },
]

const CONFIDENCE_COPY = {
  modelled: 'Directly modelled from your data.',
  projected: 'Built on the year before it — treat as a direction, not a number.',
  indicative: 'Far out. Shows the shape of the trend only.',
}

export default function Simulator({ publicMode = false }) {
  const [mode, setMode] = useState(publicMode ? 'quick' : 'mine')
  const [hasRecord, setHasRecord] = useState(!publicMode)

  useEffect(() => {
    if (publicMode) return
    api.summary()
      .then((s) => { setHasRecord(s.has_record); if (!s.has_record) setMode('quick') })
      .catch(() => {})
  }, [publicMode])

  return (
    <div className="space-y-5">
      <div>
        <p className="script text-2xl text-ink-muted">what could happen next</p>
        <h1 className="text-3xl font-semibold">Simulator</h1>
        <p className="lede mt-2 max-w-2xl text-[15px]">
          Iiris produces exploratory model estimates with uncertainty. This training cohort has no measured habits or ergonomics, so it cannot estimate the effect of changing them.
        </p>
      </div>

      {!publicMode && (
        <div className="flex gap-0.5 rounded-full border border-line-strong bg-white p-0.5
                        w-fit">
          {[['mine', 'Use my record'], ['quick', 'Enter values by hand']].map(([k, l]) => (
            <button key={k} onClick={() => setMode(k)}
                    disabled={k === 'mine' && !hasRecord}
                    className={`rounded-full px-4 py-2 text-[13px] font-medium
                                transition-colors disabled:opacity-40 ${
                      mode === k ? 'bg-ink text-sand-50' : 'text-ink-muted hover:text-ink'}`}>
              {l}
            </button>
          ))}
        </div>
      )}

      {mode === 'mine' ? <MyProjection /> : <QuickProjection publicMode={publicMode} />}
    </div>
  )
}

/* ================================================================ my record */

function MyProjection() {
  const [inputs, setInputs] = useState([])
  const [twin, setTwin] = useState(null)
  const [years, setYears] = useState(5)
  const [changes, setChanges] = useState({})
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [measure, setMeasure] = useState('se')

  useEffect(() => {
    Promise.all([api.modifiableInputs(), api.twin()])
      .then(([i, t]) => { setInputs(i.inputs.filter((x) => !x.choices && x.available)); setTwin(t) })
      .catch(setError)
  }, [])

  const run = useCallback(async (override, useChanges) => {
    setBusy(true); setError(null)
    try {
      const body = { years: override ?? years }
      const c = useChanges === undefined ? changes : useChanges
      if (Object.keys(c).length) body.changes = c
      setResult(await api.project(body))
    } catch (e) { setError(e) } finally { setBusy(false) }
  }, [years, changes])

  // First projection as soon as the twin is available.
  useEffect(() => { if (twin) run() }, [twin]) // eslint-disable-line react-hooks/exhaustive-deps

  const current = useMemo(() => twin ? {
    ...(twin.current.behaviour || {}), ...(twin.current.ergonomics || {}),
  } : {}, [twin])

  if (error && !twin) return <ErrorNote error={error} />
  if (!twin) return <Spinner label="Loading your record" />

  return (
    <div className="space-y-4">
      <Card
        title="How far ahead?"
        actions={
          <div className="flex gap-0.5 rounded-full border border-line-strong bg-white p-0.5">
            {[1, 3, 5, 8].map((y) => (
              <button key={y} onClick={() => { setYears(y); run(y) }}
                      className={`rounded-full px-3.5 py-1.5 text-[12px] font-medium
                                  transition-colors ${years === y
                          ? 'bg-ink text-sand-50' : 'text-ink-muted hover:text-ink'}`}>
                {y} yr{y > 1 ? 's' : ''}
              </button>
            ))}
          </div>
        }
      >
        <p className="mb-4 text-[13px] text-ink-muted">
          Exposure what-ifs are unavailable for this model: the training cohort has no measured behaviour or ergonomics. Baseline projections remain exploratory.
        </p>
        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
          {PRESETS.map((p) => {
            const active = JSON.stringify(changes) === JSON.stringify(p.changes)
            return (
              <button key={p.label} disabled={busy || !inputs?.length}
                      onClick={() => { setChanges(p.changes); run(undefined, p.changes) }}
                      className={`rounded-xl border p-3.5 text-left transition-all
                                  duration-200 ${active
                          ? 'border-ink bg-sand-200/60 shadow-soft'
                          : 'border-line bg-white hover:border-line-strong hover:shadow-soft'}`}>
                <span className="block text-[13.5px] font-medium">{p.label}</span>
                <span className="mt-1 block text-[11.5px] leading-relaxed text-ink-muted">
                  {p.blurb}
                </span>
              </button>
            )
          })}
        </div>

        <Collapsible label="Or set the values yourself">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {inputs.map((spec) => {
              const base = current[spec.name]
              const changed = spec.name in changes
              return (
                <SliderField
                  key={spec.name} label={spec.label} unit={spec.unit}
                  min={spec.min} max={spec.max} step={spec.step}
                  baseline={base} changed={changed}
                  value={changed ? changes[spec.name] : (base ?? (spec.min + spec.max) / 2)}
                  onChange={(v) => setChanges((c) => ({ ...c, [spec.name]: v }))}
                  onReset={() => setChanges((c) => {
                    const n = { ...c }; delete n[spec.name]; return n })}
                />
              )
            })}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <button className="btn-primary btn-sm" disabled={busy} onClick={() => run()}>
              {busy ? 'Working…' : 'Run this scenario'}
            </button>
            <button className="btn btn-ghost btn-sm"
                    onClick={() => { setChanges({}); run(undefined, {}) }}>
              Clear changes
            </button>
          </div>
        </Collapsible>

        <ErrorNote error={error} className="mt-4" />
      </Card>

      {busy && !result && <Spinner label="Projecting" />}

      {result && (
        <ProjectionResult
          history={result.history} baseline={result.baseline}
          scenario={result.scenario} measure={measure} onMeasure={setMeasure}
          appliedChanges={result.applied_changes} inputs={inputs} years={years}
        />
      )}
    </div>
  )
}

/* ================================================================= by hand */

const QUICK_BLANK = {
  age: null, spherical_equivalent: null, axial_length: null, parental_myopia: null,
  sex: '', screen_time_hours: null, near_work_min: null, outdoor_min: null,
  sleep_hours: null, viewing_distance_cm: null, continuous_session_min: null,
  posture_score: null,
}

function QuickProjection({ publicMode }) {
  const [form, setForm] = useState(QUICK_BLANK)
  const [years, setYears] = useState(5)
  const [compare, setCompare] = useState(false)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [measure, setMeasure] = useState('se')

  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }))

  // Everything except sex is numeric and shares the rule table.
  const { sex, ...numericForm } = form
  const fieldErrors = checkForm(numericForm, ['age', 'spherical_equivalent'])
  const invalid = hasErrors(fieldErrors)

  async function run(e) {
    e?.preventDefault()
    if (invalid) return
    setBusy(true); setError(null)
    const body = { years }
    for (const [k, v] of Object.entries(form)) {
      if (v === null || v === '') continue
      body[k] = k === 'sex' ? v : Number(v)
    }
    if (compare) {
      // A healthier-habits comparison, using only fields the person filled in,
      // so we never compare against a value they never gave us.
      const better = {}
      if (form.outdoor_min !== null) better.outdoor_min = Math.max(120, form.outdoor_min)
      if (form.screen_time_hours !== null)
        better.screen_time_hours = Math.min(2, form.screen_time_hours)
      if (form.viewing_distance_cm !== null)
        better.viewing_distance_cm = Math.max(40, form.viewing_distance_cm)
      if (form.continuous_session_min !== null)
        better.continuous_session_min = Math.min(20, form.continuous_session_min)
      if (Object.keys(better).length) body.compare_with = better
    }
    try { setResult(await api.quickProject(body)) }
    catch (err) { setError(err); setResult(null) } finally { setBusy(false) }
  }

  const ready = form.age !== null && form.spherical_equivalent !== null

  return (
    <div className="space-y-4">
      <Card title="Tell Iiris what you know"
            subtitle="Enter measured values only. Missing values remain unknown; this small research model has no demonstrated clinical utility.">
        <form onSubmit={run} className="space-y-6">
          <section>
            <p className="eyebrow mb-3">The essentials</p>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <NumberField name="age" label="Age" unit="yrs" step="0.5" required
                           value={form.age} onChange={set('age')} />
              <NumberField name="spherical_equivalent" label="Prescription" unit="D"
                           step="0.25" required
                           value={form.spherical_equivalent}
                           onChange={set('spherical_equivalent')}
                           hint="Negative for short-sighted, e.g. −1.50" />
              <NumberField name="axial_length" label="Eye length" unit="mm" step="0.01"
                           value={form.axial_length} onChange={set('axial_length')}
                           hint="Optional — from a biometry scan. Usually 20–30 mm." />
              <Field label="Short-sighted parents"
                     hint="One of the strongest predictors there is.">
                <select className="input" value={form.parental_myopia ?? ''}
                        onChange={(e) => set('parental_myopia')(
                          e.target.value === '' ? null : Number(e.target.value))}>
                  <option value="">Not sure</option>
                  <option value="0">Neither</option>
                  <option value="1">One</option>
                  <option value="2">Both</option>
                </select>
              </Field>
            </div>
          </section>

          <section>
            <p className="eyebrow mb-3">Daily habits (optional)</p>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <NumberField name="screen_time_hours" label="Screen time" unit="h/day"
                           step="0.5" value={form.screen_time_hours}
                           onChange={set('screen_time_hours')} />
              <NumberField name="near_work_min" label="Reading & homework"
                           unit="min/day" step="15"
                           value={form.near_work_min} onChange={set('near_work_min')} />
              <NumberField name="outdoor_min" label="Time outdoors" unit="min/day"
                           step="15"
                           value={form.outdoor_min} onChange={set('outdoor_min')} />
              <NumberField name="sleep_hours" label="Sleep" unit="h/night" step="0.5"
                           value={form.sleep_hours} onChange={set('sleep_hours')} />
              <NumberField name="viewing_distance_cm" label="Screen distance" unit="cm"
                           step="1" value={form.viewing_distance_cm}
                           onChange={set('viewing_distance_cm')} />
              <NumberField name="continuous_session_min" label="Time before a break"
                           unit="min" step="5" value={form.continuous_session_min}
                           onChange={set('continuous_session_min')} />
            </div>
          </section>

          <div className="flex flex-wrap items-center gap-4">
            <Field label="Project ahead">
              <select className="input w-auto" value={years}
                      onChange={(e) => setYears(Number(e.target.value))}>
                {[1, 2, 3, 5, 8].map((y) =>
                  <option key={y} value={y}>{y} year{y > 1 ? 's' : ''}</option>)}
              </select>
            </Field>
            <label className="mt-5 flex cursor-pointer items-center gap-2.5 text-[13px]">
              <input type="checkbox" disabled checked={compare}
                     onChange={(e) => setCompare(e.target.checked)}
                     className="h-4 w-4 rounded border-line-strong accent-ink" />
              Habit comparison unavailable for this training cohort
            </label>
          </div>

          <ErrorNote error={error} />

          {invalid && (
            <ul className="note-alert space-y-1">
              {Object.entries(fieldErrors).map(([k, v]) => <li key={k}>{v}</li>)}
            </ul>
          )}

          <button className="btn-primary btn-lg" disabled={busy || !ready || invalid}>
            {busy ? 'Working…' : 'Show me the projection'}
          </button>
        </form>
      </Card>

      {result && (
        <>
          <ProjectionResult
            history={[]} baseline={result.baseline} scenario={result.scenario}
            measure={measure} onMeasure={setMeasure}
            appliedChanges={result.scenario?.applied_changes} years={years}
            inputQuality={result.baseline.input_quality}
          />
          <div className="note-watch">{result.not_a_diagnosis}</div>
          {publicMode && (
            <Card title="Keep this, and watch it change">
              <p className="lede text-sm">
                With an account, Iiris keeps every result you add and shows the trend
                between them — which is far more informative than a single estimate.
              </p>
              <Link to="/signup" className="btn-primary btn-sm mt-4">
                Create a free account
              </Link>
            </Card>
          )}
        </>
      )}
    </div>
  )
}

/* ============================================================ shared result */

function ProjectionResult({ history, baseline, scenario, measure, onMeasure,
                            appliedChanges, inputs = [], years, inputQuality }) {
  const b = baseline.summary
  const s = scenario?.summary
  const diff = b && s ? s.final_se - b.final_se : null

  return (
    <>
      <Card
        title={`Your next ${years} year${years > 1 ? 's' : ''}`}
        actions={
          <div className="flex gap-0.5 rounded-full border border-line-strong bg-white p-0.5">
            {[['se', 'Prescription'], ['al', 'Eye length']].map(([k, l]) => (
              <button key={k} onClick={() => onMeasure(k)}
                      className={`rounded-full px-3 py-1.5 text-[12px] font-medium
                                  transition-colors ${measure === k
                          ? 'bg-ink text-sand-50' : 'text-ink-muted hover:text-ink'}`}>
                {l}
              </button>
            ))}
          </div>
        }
      >
        <ProjectionChart history={history} baseline={baseline} scenario={scenario}
                         measure={measure} />

        {/* headline outcome */}
        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="card-quiet px-4 py-3">
            <span className="eyebrow">If nothing changes</span>
            <div className="stat mt-1 text-2xl font-semibold">
              {fmt.dioptre(b?.final_se)} D
            </div>
            <div className="mt-1">
              <StatusChip label={b?.category?.label}
                          tone={toneForCategory(b?.category?.label)} />
            </div>
          </div>
          {s && (
            <div className="card-quiet border-status-calm/30 bg-status-calmBg/40 px-4 py-3">
              <span className="eyebrow">With the changes</span>
              <div className="stat mt-1 text-2xl font-semibold text-status-calm">
                {fmt.dioptre(s.final_se)} D
              </div>
              <div className="mt-1 text-[12px] text-ink-muted">
                {fmt.signed(diff)} D difference
              </div>
            </div>
          )}
          <div className="card-quiet px-4 py-3">
            <div className="flex items-center gap-1.5">
              <span className="eyebrow">Yearly pace</span>
              <Tip text="Average change per year across the whole projection." />
            </div>
            <div className="stat mt-1 text-2xl font-semibold">
              {fmt.signed(b?.mean_annual_se_change)}
              <span className="ml-1 text-sm font-normal text-ink-muted">D/yr</span>
            </div>
          </div>
          <div className="card-quiet px-4 py-3">
            <span className="eyebrow">Eye length then</span>
            <div className="stat mt-1 text-2xl font-semibold">{fmt.mm(b?.final_al)}
              <span className="ml-1 text-sm font-normal text-ink-muted">mm</span></div>
            <div className="mt-1 text-[12px] text-ink-muted">
              {fmt.signed(b?.total_al_change)} mm over {years} yr
            </div>
          </div>
        </div>

        {appliedChanges && Object.keys(appliedChanges).length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {Object.entries(appliedChanges).map(([k, v]) => {
              const spec = inputs.find((i) => i.name === k)
              return (
                <StatusChip key={k} tone="outline"
                            label={`${spec?.label || k.replace(/_/g, ' ')}: ${
                              fmt.num(v, 1)}${spec?.unit ? ' ' + spec.unit : ''}`} />
              )
            })}
          </div>
        )}

        <div className="mt-4 note-quiet">
          <strong className="font-semibold text-ink">About the widening band. </strong>
          {baseline.projection_disclaimer}
        </div>
        <Disclaimer text={baseline.disclaimer} />
        <ul className="mt-3 list-disc pl-5 text-xs text-ink-muted">{baseline.warnings?.map(w => <li key={w}>{w}</li>)}</ul>
      </Card>

      <Card title="Year by year"
            subtitle="Confidence drops the further out you look — that is shown, not hidden.">
        <div className="overflow-x-auto">
          <table className="table">
            <thead>
              <tr>
                <th>Year</th><th>Prescription</th><th>Likely range</th>
                <th>Eye length</th>{s && <th>With changes</th>}<th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {baseline.points.map((p, i) => (
                <tr key={p.step}>
                  <td className="font-medium">
                    {new Date(`${p.date}T00:00:00`).getFullYear()}
                    <span className="ml-1.5 text-[11px] text-ink-faint">
                      +{p.years_ahead}y</span>
                  </td>
                  <td className="stat font-medium">{fmt.dioptre(p.spherical_equivalent)} D</td>
                  <td className="stat text-ink-muted">
                    {fmt.dioptre(p.se_upper)} to {fmt.dioptre(p.se_lower)}
                  </td>
                  <td className="stat">{fmt.mm(p.axial_length)} mm</td>
                  {s && (
                    <td className="stat font-medium text-status-calm">
                      {fmt.dioptre(scenario.points[i]?.spherical_equivalent)} D
                    </td>
                  )}
                  <td>
                    <StatusChip
                      label={p.confidence}
                      tone={p.confidence === 'modelled' ? 'calm'
                        : p.confidence === 'projected' ? 'outline' : 'neutral'} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <dl className="mt-4 grid gap-2 sm:grid-cols-3">
          {Object.entries(CONFIDENCE_COPY).map(([k, v]) => (
            <div key={k} className="text-[12px] leading-relaxed text-ink-muted">
              <dt className="font-medium text-ink">{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      </Card>

      {inputQuality && (
        <Card title="What this estimate rests on">
          <ul className="space-y-2">
            {inputQuality.notes.map((n, i) => (
              <li key={i} className="flex gap-2.5 text-[13px] leading-relaxed
                                     text-ink-muted">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-sand-500" />
                {n}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  )
}

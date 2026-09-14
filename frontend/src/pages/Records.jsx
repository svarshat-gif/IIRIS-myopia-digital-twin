import React, { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, fmt, seDirection } from '../lib/api'
import {
  Card, Collapsible, Disclaimer, EmptyState, ErrorNote, Field, NumberField,
  SkeletonCard, StatusChip, Tip, toneForCategory, useToast,
} from '../components/ui'
import { checkForm, hasErrors } from '../lib/validate'
import Attachments from '../components/Attachments'

const TREATMENTS = [
  ['none', 'None'], ['single_vision', 'Ordinary glasses'],
  ['atropine', 'Atropine drops'], ['ortho_k', 'Ortho-K lenses'],
  ['dims', 'Myopia-control glasses'],
]
const today = () => new Date().toISOString().slice(0, 10)

const BLANK = {
  visit_date: today(), spherical_equivalent: null, axial_length: null,
  visual_acuity: null, treatment: 'none', age: null,
  screen_time_hours: null, near_work_min: null, outdoor_min: null, sleep_hours: null,
  viewing_distance_cm: null, posture_score: null, continuous_session_min: null,
}

export default function Records() {
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [adding, setAdding] = useState(params.get('add') === '1')
  const toast = useToast()

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try { setData(await api.records()) }
    catch (e) { setError(e) } finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])

  function closeForm() {
    setAdding(false)
    if (params.get('add')) { params.delete('add'); setParams(params, { replace: true }) }
  }

  async function remove(id, date) {
    if (!window.confirm(`Delete the result from ${fmt.date(date)}? This cannot be undone.`))
      return
    try {
      await api.deleteRecord(id)
      toast('Result deleted')
      load()
    } catch (e) { setError(e) }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="script text-2xl text-ink-muted">everything so far</p>
          <h1 className="text-3xl font-semibold">My records</h1>
        </div>
        {!adding && (
          <button className="btn-primary" onClick={() => setAdding(true)}>
            + Add a result
          </button>
        )}
      </div>

      {adding && <AddForm onClose={closeForm} onSaved={(r) => {
        closeForm(); load()
        toast(r.previous_version
          ? `Saved — your record is now version ${r.twin_version}`
          : 'Saved — your record has started')
      }} />}

      <ErrorNote error={error} onRetry={load} />

      <Attachments />

      {loading ? <SkeletonCard lines={6} />
        : !data?.records?.length ? (
          <Card>
            <EmptyState title="No results yet"
                        action={<button className="btn-primary"
                                        onClick={() => setAdding(true)}>
                          Add my first result</button>}>
              Once you add a result from an eye test, it will appear here — newest
              first, with the change since the visit before it.
            </EmptyState>
          </Card>
        ) : (
          <div className="space-y-3 stagger">
            {data.records.map((r, i) => (
              <RecordCard key={r.observation_id} record={r} latest={i === 0}
                          onDelete={() => remove(r.observation_id, r.visit_date)} />
            ))}
          </div>
        )}
    </div>
  )
}

/* ------------------------------------------------------------- one record */

function RecordCard({ record: r, latest, onDelete }) {
  const change = r.change
  const tone = !change ? 'neutral'
    : change.spherical_equivalent <= -0.5 ? 'alert'
    : change.spherical_equivalent <= -0.25 ? 'watch' : 'calm'

  const habits = [
    ['Screen time', r.screen_time_hours, 'h/day'],
    ['Reading & homework', r.near_work_min, 'min/day'],
    ['Time outdoors', r.outdoor_min, 'min/day'],
    ['Sleep', r.sleep_hours, 'h/night'],
    ['Screen distance', r.viewing_distance_cm, 'cm'],
    ['Posture', r.posture_score, ''],
    ['Time before a break', r.continuous_session_min, 'min'],
  ]
  const recorded = habits.filter(([, v]) => v !== null && v !== undefined)

  return (
    <Card className={latest ? 'ring-1 ring-ink/10' : ''}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold">{fmt.date(r.visit_date)}</h2>
            {latest && <StatusChip label="Most recent" tone="outline" />}
            <StatusChip label={r.category?.label} tone={toneForCategory(r.category?.label)} />
          </div>
          {r.age && <p className="mt-0.5 text-[13px] text-ink-muted">
            Age {fmt.num(r.age, 1)}</p>}
        </div>
        <button onClick={onDelete}
                className="text-[12px] text-ink-faint underline underline-offset-2
                           hover:text-status-alert">
          Delete
        </button>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <div className="card-quiet px-4 py-3">
          <div className="flex items-center gap-1.5">
            <span className="eyebrow">Prescription</span>
            <Tip text="Spherical equivalent in dioptres. More negative means more short-sighted." />
          </div>
          <div className="stat mt-1 text-xl font-semibold">
            {fmt.dioptre(r.spherical_equivalent)} <span
              className="text-sm font-normal text-ink-muted">D</span>
          </div>
          {change && (
            <div className={`mt-1 text-[12px] ${
              tone === 'alert' ? 'text-status-alert'
                : tone === 'watch' ? 'text-status-watch' : 'text-status-calm'}`}>
              {fmt.signed(change.spherical_equivalent)} D — {
                seDirection(change.spherical_equivalent)}
            </div>
          )}
        </div>

        <div className="card-quiet px-4 py-3">
          <div className="flex items-center gap-1.5">
            <span className="eyebrow">Eye length</span>
            <Tip text="Axial length in millimetres, from a biometry scan." />
          </div>
          <div className="stat mt-1 text-xl font-semibold">
            {fmt.mm(r.axial_length)} <span
              className="text-sm font-normal text-ink-muted">mm</span>
          </div>
          {change && (
            <div className="mt-1 text-[12px] text-ink-muted">
              {fmt.signed(change.axial_length, 2)} mm over {change.months} months
            </div>
          )}
        </div>

        <div className="card-quiet px-4 py-3">
          <span className="eyebrow">Treatment</span>
          <div className="mt-1 text-[15px] font-medium">
            {TREATMENTS.find(([v]) => v === r.treatment)?.[1] || r.treatment || '—'}
          </div>
          {r.visual_acuity !== null && r.visual_acuity !== undefined && (
            <div className="mt-1 text-[12px] text-ink-muted">
              Vision {fmt.num(r.visual_acuity, 2)} logMAR
            </div>
          )}
        </div>
      </div>

      <div className="mt-4">
        <Collapsible label={recorded.length
          ? `Habits recorded at this visit (${recorded.length})`
          : 'No habits recorded at this visit'}>
          {recorded.length ? (
            <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
              {recorded.map(([label, value, unit]) => (
                <div key={label}
                     className="flex items-baseline justify-between gap-3
                                border-b border-line/70 pb-1.5 text-[13px]">
                  <dt className="text-ink-muted">{label}</dt>
                  <dd className="stat font-medium">
                    {fmt.num(value, 1)} <span className="text-[11px] font-normal
                      text-ink-faint">{unit}</span>
                  </dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-[13px] text-ink-muted">
              Nothing was recorded about screen time, reading or time outdoors at this
              visit. That is fine — Iiris leaves it blank rather than guessing.
            </p>
          )}
        </Collapsible>
      </div>
    </Card>
  )
}

/* ------------------------------------------------------------- add a result */

function AddForm({ onClose, onSaved }) {
  const [form, setForm] = useState(BLANK)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }))

  const { visit_date, treatment, ...numericForm } = form
  const fieldErrors = checkForm(numericForm,
                                ['spherical_equivalent', 'axial_length'])
  const invalid = hasErrors(fieldErrors)
  const canSave = !!form.visit_date && !invalid

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setError(null)
    // Nulls are dropped, so a blank box is stored as "not measured", never as 0.
    const payload = { source: 'ui' }
    for (const [k, v] of Object.entries(form)) {
      if (v === null || v === '') continue
      payload[k] = k === 'visit_date' || k === 'treatment' ? v : Number(v)
    }
    try { onSaved(await api.addRecord(payload)) }
    catch (err) { setError(err) } finally { setBusy(false) }
  }

  return (
    <Card title="Add an eye test result"
          subtitle="Fill in what you have. Anything you leave blank stays blank."
          actions={<button className="btn btn-ghost btn-sm" onClick={onClose}>
            Cancel</button>}>
      <form onSubmit={submit} className="space-y-6">
        <section>
          <p className="eyebrow mb-3">From your prescription</p>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Date of test" required>
              <input className="input" type="date" max={today()} required
                     value={form.visit_date}
                     onChange={(e) => set('visit_date')(e.target.value)} />
            </Field>
            <NumberField name="spherical_equivalent" label="Prescription" unit="D"
                         required step="0.25"
                         value={form.spherical_equivalent}
                         onChange={set('spherical_equivalent')}
                         placeholder="-2.50"
                         hint="Sphere + half the cylinder. Negative for short-sighted." />
            <NumberField name="axial_length" label="Eye length" unit="mm" required
                         step="0.01"
                         value={form.axial_length} onChange={set('axial_length')}
                         placeholder="24.30"
                         hint="From a biometry scan. Usually 20–30 mm." />
            <NumberField name="age" label="Your age" unit="yrs" step="0.5"
                         value={form.age} onChange={set('age')} placeholder="12" />
            <NumberField name="visual_acuity" label="Vision" unit="logMAR" step="0.01"
                         value={form.visual_acuity} onChange={set('visual_acuity')}
                         placeholder="0.00" hint="Optional. 0.00 is 6/6." />
            <Field label="Treatment">
              <select className="input" value={form.treatment}
                      onChange={(e) => set('treatment')(e.target.value)}>
                {TREATMENTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </Field>
          </div>
        </section>

        <section>
          <p className="eyebrow mb-1">Your daily habits</p>
          <p className="mb-3 text-[12.5px] text-ink-muted">
            Optional, but this is what makes the simulator useful for you.
          </p>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <NumberField name="screen_time_hours" label="Screen time" unit="h/day"
                         step="0.5" value={form.screen_time_hours}
                         onChange={set('screen_time_hours')} placeholder="5" />
            <NumberField name="near_work_min" label="Reading & homework"
                         unit="min/day" step="15"
                         value={form.near_work_min} onChange={set('near_work_min')}
                         placeholder="240" />
            <NumberField name="outdoor_min" label="Time outdoors" unit="min/day"
                         step="15" value={form.outdoor_min}
                         onChange={set('outdoor_min')} placeholder="60" />
            <NumberField name="sleep_hours" label="Sleep" unit="h/night" step="0.5"
                         value={form.sleep_hours} onChange={set('sleep_hours')}
                         placeholder="8.5" />
          </div>
        </section>

        <section>
          <p className="eyebrow mb-1">Your screen setup</p>
          <p className="mb-3 text-[12.5px] text-ink-muted">
            Rough estimates are fine — these are not clinical measurements.
          </p>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <NumberField name="viewing_distance_cm" label="Screen or book distance"
                         unit="cm" step="1"
                         value={form.viewing_distance_cm}
                         onChange={set('viewing_distance_cm')} placeholder="30" />
            <NumberField name="continuous_session_min" label="Time before a break"
                         unit="min" step="5"
                         value={form.continuous_session_min}
                         onChange={set('continuous_session_min')} placeholder="45" />
            <NumberField name="posture_score" label="Posture" unit="0–1" step="0.05"
                         value={form.posture_score} onChange={set('posture_score')}
                         placeholder="0.7" hint="1 means upright and well supported." />
          </div>
        </section>

        <ErrorNote error={error} />

        <div className="flex flex-wrap items-center gap-3">
          <button className="btn-primary" disabled={busy || !canSave}>
            {busy ? 'Saving…' : 'Save result'}
          </button>
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
          {!canSave && !invalid && (
            <span className="text-[12.5px] text-ink-faint">
              Date, prescription and eye length are needed to save.
            </span>
          )}
          {invalid && (
            <span className="text-[12.5px] text-status-alert">
              {Object.values(fieldErrors)[0]}
            </span>
          )}
        </div>
        <Disclaimer text="Iiris stores what you enter so it can show you a trend. It is not an eye test and it does not diagnose." />
      </form>
    </Card>
  )
}

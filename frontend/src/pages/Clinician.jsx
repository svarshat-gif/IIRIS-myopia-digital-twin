import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, fmt } from '../lib/api'
import { Card, Disclaimer, EmptyState, ErrorNote, Field, NumberField, SkeletonCard, StatusChip, toneForBand } from '../components/ui'
import { checkForm, hasErrors } from '../lib/validate'

import ForecastPanel from '../components/ForecastPanel'

export function Cohort() {
  const [patients, setPatients] = useState(null)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  useEffect(() => { let alive = true; api.cohort().then(x => alive && setPatients(x)).catch(e => alive && setError(e)); return () => { alive = false } }, [])
  const shown = patients?.filter(p => `${p.external_key || ''} ${p.patient_id}`.toLowerCase().includes(search.toLowerCase()) && (!status || toneForBand(p.risk_band) === status))
  return <div className="space-y-5">
    <div><p className="script text-2xl text-ink-muted">a shared view</p><h1 className="text-3xl font-semibold">Patient cohort</h1><p className="lede mt-2">Records assigned to your account. Risk stays unavailable when the model cannot estimate it.</p></div>
    <ErrorNote error={error} />
    <Card title="Find a record"><div className="grid gap-3 sm:grid-cols-2">
      <Field label="Search by study key"><input className="input" type="search" value={search} onChange={e => setSearch(e.target.value)} /></Field>
      <Field label="Model risk status"><select className="input" value={status} onChange={e => setStatus(e.target.value)}><option value="">All statuses</option><option value="calm">Calm</option><option value="watch">Watch</option><option value="alert">Alert</option><option value="neutral">Unavailable</option></select></Field>
    </div></Card>
    {!patients ? !error && <SkeletonCard lines={6} /> : !shown.length ? <Card><EmptyState title="No matching records">Try another study key or ask an administrator to assign records.</EmptyState></Card> :
      <Card title={`${shown.length} records`}><div className="overflow-x-auto"><table className="table">
        <thead><tr><th scope="col">Study key</th><th scope="col">Visits</th><th scope="col">Twin</th><th scope="col">Latest SE</th><th scope="col">Status</th><th scope="col">Source</th></tr></thead>
        <tbody>{shown.map(p => <tr key={p.patient_id}><th scope="row"><Link className="underline underline-offset-2" to={`/app/cohort/${p.patient_id}`}>{p.external_key || p.patient_id}</Link></th><td>{p.n_visits}</td><td>v{p.twin_version}</td><td>{fmt.num(p.latest_se)} D</td><td><StatusChip tone={toneForBand(p.risk_band)} label={p.risk_band || 'Unavailable'} /></td><td>{p.data_source}</td></tr>)}</tbody>
      </table></div></Card>}
  </div>
}

export function PatientDetail() {
  const { patientId } = useParams()
  const [twin, setTwin] = useState(null)
  const [loadedFor, setLoadedFor] = useState(null)
  const loadSequence = useRef(0)
  const [versions, setVersions] = useState([])
  const [explanation, setExplanation] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [question, setQuestion] = useState('What changed since the last visit?')
  const [answer, setAnswer] = useState(null)
  const [diff, setDiff] = useState(null)
  const [scenario, setScenario] = useState(null)
  const [form, setForm] = useState({ spherical_equivalent: null, axial_length: null, visit_date: '', followup_month: null })
  const [validation, setValidation] = useState({})
  const loadForecast = useCallback((months, options) => api.patientPrediction(patientId, months, options), [patientId])
  const load = useCallback(async () => {
    const sequence = ++loadSequence.current
    try {
      const [t, v, e] = await Promise.all([api.patientTwin(patientId), api.patientVersions(patientId), api.patientExplanation(patientId)])
      if (sequence !== loadSequence.current) return
      setTwin(t); setLoadedFor(patientId); setVersions(v.versions); setExplanation(e); setError(null)
    } catch (e) { if (sequence === loadSequence.current) setError(e) }
  }, [patientId])
  useEffect(() => {
    setError(null); setAnswer(null); setDiff(null); setScenario(null)
    load()
    return () => { loadSequence.current += 1 }
  }, [load])
  async function submitVisit(e) {
    e.preventDefault()
    const errors = checkForm(form, ['spherical_equivalent', 'axial_length'])
    setValidation(errors)
    if (hasErrors(errors)) return
    setBusy(true); setError(null)
    try {
      const relative = twin.current.visit_date === null
      const payload = { spherical_equivalent: form.spherical_equivalent, axial_length: form.axial_length,
        ...(relative ? { followup_month: form.followup_month } : { visit_date: form.visit_date }) }
      await api.patientVisit(patientId, payload)
      setAnswer(null); setDiff(null); setScenario(null)
      setForm({ spherical_equivalent: null, axial_length: null, visit_date: '', followup_month: null })
      await load()
    } catch (err) { setError(err) } finally { setBusy(false) }
  }
  async function ask(e) {
    e.preventDefault(); setBusy(true); setError(null)
    try { setAnswer(await api.patientQuery(patientId, question)) } catch (err) { setError(err) } finally { setBusy(false) }
  }
  async function compare() {
    setBusy(true)
    try { setDiff(await api.patientDiff(patientId, versions.at(-2).version, versions.at(-1).version)) } catch (err) { setError(err) } finally { setBusy(false) }
  }
  async function runScenario() {
    setBusy(true); setError(null)
    try { setScenario(await api.patientScenarios(patientId, [{ label: 'Outdoor exposure', changes: { outdoor_min: 120 } }, { label: 'Viewing distance', changes: { viewing_distance_cm: 40 } }])) } catch (err) { setError(err) } finally { setBusy(false) }
  }
  if (!twin || loadedFor !== patientId) return <><ErrorNote error={error} onRetry={load} />{!error && <SkeletonCard lines={8} />}</>
  return <div className="space-y-5">
    <Link className="text-sm underline underline-offset-2" to="/app/cohort">Back to cohort</Link>
    <div><p className="script text-2xl text-ink-muted">the evolving record</p><h1 className="break-all text-3xl font-semibold">{twin.patient.external_key || 'Patient detail'}</h1>
      <p className="lede mt-2">Twin v{twin.version} · {twin.patient.data_source}</p></div>
    <ErrorNote error={error} />
    <Card title="Current twin"><dl className="grid gap-3 text-sm sm:grid-cols-3"><div><dt className="eyebrow">Spherical equivalent</dt><dd>{twin.current.spherical_equivalent} D</dd></div><div><dt className="eyebrow">Axial length</dt><dd>{twin.current.axial_length} mm</dd></div><div><dt className="eyebrow">Visit time</dt><dd>{twin.current.visit_date ? fmt.date(twin.current.visit_date) : `Month ${twin.current.followup_month} since baseline`}</dd></div></dl>
      <p className="note-watch mt-4" role="status">Monitor: {twin.monitor?.materially_changed ? twin.monitor.flags.join('; ') : twin.monitor?.note || 'No material change flagged'}</p>
      <details className="mt-4 text-sm"><summary className="cursor-pointer">Full state and measured history</summary><div className="mt-3 overflow-x-auto"><table className="table"><thead><tr><th scope="col">Visit time</th><th scope="col">SE (D)</th><th scope="col">AL (mm)</th><th scope="col">Recorded age</th><th scope="col">Treatment</th></tr></thead><tbody>{twin.history.map((v, i) => <tr key={i}><th scope="row">{v.visit_date || `Month ${v.followup_month}`}</th><td>{v.spherical_equivalent}</td><td>{v.axial_length}</td><td>{v.age ?? 'Missing'}</td><td>{v.treatment ?? 'Missing'}</td></tr>)}</tbody></table><p className="mt-3">Recent SE trend: {fmt.num(twin.derived.se_slope_per_year, 3)} D/year. Recent AL trend: {fmt.num(twin.derived.al_slope_per_year, 3)} mm/year. Model: {twin.model_version}.</p></div></details>
    </Card>
    <Card title="Trajectory and uncertainty"><ForecastPanel history={twin.history} loadPrediction={loadForecast} recordKey={`${patientId}:${twin.version}`} />
      <Disclaimer text={twin.disclaimer} />
    </Card>
    <Card title="Prediction attribution" subtitle={explanation?.method === 'shap' ? 'SHAP feature attribution' : 'Feature ablation attribution; this is not an exact Shapley value'}><div className="overflow-x-auto"><table className="table"><thead><tr><th scope="col">Factor</th><th scope="col">Contribution</th></tr></thead><tbody>{explanation?.contributions?.map(c => <tr key={c.feature}><th scope="row">{c.label}</th><td>{fmt.num(c.contribution, 3)}</td></tr>)}</tbody></table></div><Disclaimer text={explanation?.attribution_disclaimer} /></Card>
    <Card title="Version history" actions={<button className="btn btn-secondary btn-sm" disabled={busy || versions.length < 2} onClick={compare}>Compare latest versions</button>}>
      <ol className="space-y-2 text-sm">{versions.map(v => <li key={v.version}>v{v.version} · {v.triggered_by} · {fmt.date(v.created_at)}</li>)}</ol>
      {diff && <div className="mt-4 space-y-2 text-sm" role="status">{diff.observed_changes?.map(c => <p key={c.field}>{c.field}: {c.from ?? 'missing'} → {c.to ?? 'missing'} {c.unit}</p>)}</div>}
    </Card>
    <Card title="Add a new observation" subtitle="This saves a new twin version, recalculates the prediction and records a monitor flag.">
      <form onSubmit={submitVisit} className="space-y-4">
        {twin.current.visit_date === null ? <NumberField label="Source-recorded month since baseline" name="followup_month" min={0} max={600} step="any" required value={form.followup_month} onChange={v => setForm({ ...form, followup_month: v })} hint="Calendar dates are absent from this research source. Enter an actual recorded follow-up month." /> : <Field label="Visit date" required><input className="input" type="date" required value={form.visit_date} max={new Date().toISOString().slice(0, 10)} onChange={e => setForm({ ...form, visit_date: e.target.value })} /></Field>}
        <div className="grid gap-3 sm:grid-cols-2"><NumberField label="Spherical equivalent" name="spherical_equivalent" unit="D" required step="any" value={form.spherical_equivalent} error={validation.spherical_equivalent} onChange={v => setForm({ ...form, spherical_equivalent: v })} /><NumberField label="Axial length" name="axial_length" unit="mm" required step="any" value={form.axial_length} error={validation.axial_length} onChange={v => setForm({ ...form, axial_length: v })} /></div>
        <button className="btn-primary" disabled={busy}>Save observation</button>
      </form>
    </Card>
    <Card title="Scenario comparison" subtitle="This cohort has no measured behaviour or ergonomic layer. Numeric exposure effects are unavailable.">
      <button className="btn btn-secondary" onClick={runScenario} disabled={busy}>Check scenario availability</button>
      {scenario && <div className="mt-4 space-y-2 text-sm" role="status">{scenario.rejected?.map(s => <p key={s.label}><strong>{s.label}: </strong>{s.errors.join(' ')}</p>)}</div>}
    </Card>
    <Card title="Agent console" subtitle="Deterministic tools, an auditable trace, and cited evidence.">
      <form onSubmit={ask} className="space-y-3"><Field label="Question"><textarea className="input" required minLength={3} maxLength={1000} value={question} onChange={e => setQuestion(e.target.value)} /></Field><button className="btn-primary" disabled={busy}>Ask the twin</button></form>
      {answer && <div className="mt-4 space-y-3 text-sm" aria-live="polite"><p className="whitespace-pre-wrap">{answer.answer}</p><ol className="list-decimal space-y-2 pl-5">{answer.trace.map((t, i) => <li key={i}>{t.tool} · {t.status} · {t.why}{t.error && <p className="text-status-watch">{t.error}</p>}</li>)}</ol>
        {answer.facts?.retrieve_evidence?.results?.map(c => <p key={c.external_id}><a className="underline" href={c.url} target="_blank" rel="noreferrer">{c.title}</a> · {c.external_id} {c.doi && `· DOI ${c.doi}`}</p>)}<Disclaimer text={answer.disclaimer} /></div>}
    </Card>
  </div>
}

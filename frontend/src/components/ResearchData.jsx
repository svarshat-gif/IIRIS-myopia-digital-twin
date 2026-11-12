import React, { useState } from 'react'
import { api, fmt } from '../lib/api'
import { Card, Disclaimer, ErrorNote, Field, NumberField } from './ui'

export default function ResearchData({ catalog, model }) {
  const [form, setForm] = useState({ age: null, spheq: null, al: null,
    gender: null, mommy: null, dadmy: null, sporthr: null, readhr: null,
    comphr: null, studyhr: null, tvhr: null })
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  async function submit(e) {
    e.preventDefault(); setBusy(true); setError(null); setResult(null)
    try { setResult(await api.onsetPrediction(form)) } catch (err) { setError(err) } finally { setBusy(false) }
  }
  return <>
    <Card title="Additional research datasets" subtitle="Each source has its own role; these are not additional DIMS follow-up visits.">
      <div className="overflow-x-auto"><table className="table">
        <thead><tr><th scope="col">Dataset</th><th scope="col">Records</th><th scope="col">Role</th><th scope="col">License</th></tr></thead>
        <tbody>{catalog?.datasets?.map(d => <tr key={d.id}><th scope="row"><a className="underline" href={d.source_url} target="_blank" rel="noreferrer">{d.name}</a></th><td>{d.n_patients ? `${d.n_patients} source subject IDs / ${d.rows} rows` : `${d.rows} rows; subjects unverified`}</td><td>{d.role}</td><td>{d.license}</td></tr>)}</tbody>
      </table></div>
      {catalog?.datasets?.map(d => <details key={d.id} className="mt-3 text-sm"><summary className="cursor-pointer">{d.name}: limits</summary><ul className="mt-2 list-disc pl-5 text-ink-muted">{d.limitations.map(x => <li key={x}>{x}</li>)}</ul></details>)}
      <p className="mt-3 text-sm text-ink-muted">{catalog?.note}</p>
      <p className="mt-3 text-xs text-ink-muted">Excluded: {catalog?.excluded?.map(d => `${d.id}: ${d.reason}`).join('; ')}.</p>
    </Card>
    {model?.metrics && <Card title="Five-year onset research model" subtitle="A separate model for initially nonmyopic children aged 5-9. This does not replace the progression forecast.">
      <p className="text-sm">OLSM: {model.n_patients} children, {model.n_positive} onsets. Fit/calibration/test: {model.split.train_patients}/{model.split.calibration_patients}/{model.split.test_patients}. {model.calibration}.</p>
      <div className="mt-4 overflow-x-auto"><table className="table"><thead><tr><th scope="col">Inputs</th><th scope="col">Test ROC AUC (95% bootstrap CI)</th><th scope="col">Brier score</th><th scope="col">Prevalence baseline Brier</th><th scope="col">Accuracy</th><th scope="col">Sensitivity</th><th scope="col">Balanced accuracy</th></tr></thead><tbody>{Object.entries(model.metrics).map(([k, v]) => <tr key={k}><th scope="row">{k.replace('_', ' + ')}</th><td>{v.roc_auc} [{v.bootstrap_95ci.roc_auc.join(', ')}]</td><td>{v.brier}</td><td>{v.prevalence_baseline.brier}</td><td>{fmt.num(v.accuracy * 100, 1)}%</td><td>{fmt.num(v.sensitivity * 100, 1)}%</td><td>{fmt.num(v.balanced_accuracy * 100, 1)}%</td></tr>)}</tbody></table></div>
      <p className="note-watch mt-4">Classification metrics use a fixed 0.5 probability threshold. Predicting no onset for every child already gives {fmt.num(model.metrics.clinical.prevalence_baseline.accuracy * 100, 1)}% accuracy and 0% sensitivity. Overall accuracy above 95% has not been achieved. Small historical single-cohort holdout; no external validation. The activity score difference does not establish an intervention effect or a reliable improvement.</p>
      <details className="mt-4"><summary className="cursor-pointer text-sm">Try an onset research estimate</summary>
        <form className="mt-4 space-y-4" onSubmit={submit}>
          <div className="grid gap-3 sm:grid-cols-3">{[
            ['age', 'Baseline age', 'years', 5, 9], ['spheq', 'Baseline spherical equivalent', 'D', -.749, 15], ['al', 'Measured baseline axial length', 'mm', 15, 35],
          ].map(([name, label, unit, min, max]) => <NumberField key={name} name={name} label={label} unit={unit} min={min} max={max} step="any" required value={form[name]} onChange={v => setForm({ ...form, [name]: v })} />)}</div>
          <div className="grid gap-3 sm:grid-cols-3">{[['gender', 'Recorded sex'], ['mommy', 'Mother myopic'], ['dadmy', 'Father myopic']].map(([name, label]) => <Field key={name} label={label}><select className="input" value={form[name] ?? ''} onChange={e => setForm({ ...form, [name]: e.target.value === '' ? null : Number(e.target.value) })}><option value="">Unknown / not recorded</option><option value="0">{name === 'gender' ? 'Male' : 'No'}</option><option value="1">{name === 'gender' ? 'Female' : 'Yes'}</option></select></Field>)}</div>
          <p className="text-sm text-ink-muted">Optional measured activity, in hours per week. All five are required to use the activity model. Sports/outdoor activity is a combined source field.</p>
          <div className="grid gap-3 sm:grid-cols-2">{[['sporthr', 'Sports / outdoor activity'], ['readhr', 'Pleasure reading'], ['comphr', 'Computer / games'], ['studyhr', 'School study'], ['tvhr', 'Television']].map(([name, label]) => <NumberField key={name} name={name} label={label} unit="h/week" min={0} max={168} step="any" value={form[name]} onChange={v => setForm({ ...form, [name]: v })} />)}</div>
          <button className="btn-primary" disabled={busy}>Estimate five-year onset association</button>
          <ErrorNote error={error} />
          {result && <div role="status" className="note-watch"><p>Five-year onset estimate: {fmt.num(result.probability * 100, 1)}%. Inputs: {result.model}. No individual probability interval has been validated.</p><ul className="mt-2 list-disc pl-5">{result.warnings.map(w => <li key={w}>{w}</li>)}</ul></div>}
        </form>
      </details>
      <Disclaimer text={model.disclaimer} />
    </Card>}
  </>
}

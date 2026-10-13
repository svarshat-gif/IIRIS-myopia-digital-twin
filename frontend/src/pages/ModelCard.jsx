import React, { useEffect, useState } from 'react'
import { api, fmt } from '../lib/api'
import { Card, Disclaimer, ErrorNote, SkeletonCard, StatusChip } from '../components/ui'

export default function ModelCard() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => { let alive = true; api.modelCard().then(x => alive && setData(x))
    .catch(e => alive && setError(e)); return () => { alive = false } }, [])
  if (error) return <ErrorNote error={error} />
  if (!data) return <SkeletonCard lines={8} />
  const metrics = data.metrics
  return <div className="space-y-5">
    <div><p className="script text-2xl text-ink-muted">what the evidence supports</p>
      <h1 className="text-3xl font-semibold">Model card</h1></div>
    <Card title="Training provenance" subtitle={`Trained on: ${data.data_source}`}>
      <StatusChip label="Exploratory research model" tone="watch" />
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
        <div><dt className="eyebrow">Independent patients</dt><dd>{metrics.n_patients}</dd></div>
        <div><dt className="eyebrow">Visits</dt><dd>{metrics.n_visits}</dd></div>
        <div><dt className="eyebrow">Training date</dt><dd>{fmt.date(data.trained_at)}</dd></div>
        <div><dt className="eyebrow">Version</dt><dd className="break-all">{data.model_version}</dd></div>
      </dl>
      <p className="mt-4 text-sm text-ink-muted">{metrics.split.strategy}. Training: {metrics.split.train_patients}; calibration: {metrics.split.val_patients}; test: {metrics.split.test_patients} patients.</p>
      {(data.provenance?.sources || []).map(s => <p key={s.doi} className="mt-3 text-sm">
        <a className="underline underline-offset-2" href={`https://doi.org/${s.doi}`} target="_blank" rel="noreferrer">{s.doi}</a> · {s.license}</p>)}
    </Card>
    <Card title="Held-out results" subtitle="A high R² does not establish clinical usefulness. Lower MAE is better; compare carry-forward first.">
      <div className="overflow-x-auto"><table className="table"><caption className="sr-only">Patient-grouped model and baseline evaluation</caption>
        <thead><tr><th scope="col">Target</th><th scope="col">Model MAE</th><th scope="col">Carry-forward MAE</th><th scope="col">Ridge MAE</th><th scope="col">RMSE</th><th scope="col">R²</th><th scope="col">Coverage</th></tr></thead>
        <tbody>{Object.entries(metrics.regression).map(([target, m]) => <tr key={target}>
          <th scope="row">{target.replace('y_', '').replace('_', ' · ')} ({target.includes('se') ? 'D' : 'mm'})</th>
          <td>{m.mae}<span className="block text-xs text-ink-muted">95% bootstrap CI: {m.bootstrap_95ci?.mae?.join(' to ') ?? 'unavailable'}</span></td>
          <td>{m.baselines.carry_forward.mae}</td><td>{m.baselines.ridge.mae}</td><td>{m.rmse}</td><td>{m.r2}</td>
          <td>{fmt.num(m.interval_coverage * 100, 1)}% / nominal {fmt.num(m.nominal_coverage * 100, 0)}%</td></tr>)}</tbody></table></div>
      <p className="note-watch mt-4">Only {metrics.split.test_patients} test patients. Bootstrap intervals are unstable at this sample size. The current 12-month models do not outperform carry-forward. This model has no demonstrated clinical utility.</p>
      <Disclaimer text="Model estimates for decision support only. Not a diagnosis, prescription, medical device or causal treatment effect." />
    </Card>
    <Card title="Ablation and uncertainty">
      {Object.entries(metrics.ablation || {}).map(([name, result]) => <p key={name} className="mb-3 text-sm"><strong>{name}: </strong>
        {result.reason || `SE 12-month MAE ${result.y_se_12m?.mae ?? 'not evaluable'} D`}</p>)}
      <p className="text-sm text-ink-muted">Development cross-validation groups patients. Interval calibration uses separate patients and each patient's maximum nonconformity score. Reported coverage is measured on the untouched test patients. Multi-year rollout bands are heuristic and are not calibrated beyond the first year.</p>
    </Card>
    <Card title="Limits"><ul className="list-disc space-y-2 pl-5 text-sm text-ink-muted">{data.limitations.map(x => <li key={x}>{x}</li>)}</ul></Card>
  </div>
}

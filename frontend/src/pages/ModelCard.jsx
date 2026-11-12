import React, { useEffect, useState } from 'react'
import { api, fmt } from '../lib/api'
import { Card, Disclaimer, ErrorNote, SkeletonCard, StatusChip } from '../components/ui'
import ResearchData from '../components/ResearchData'

function SelectableForecastResults({ report }) {
  if (!report) return null
  const range = report.request_range_months || [1, 120]
  const observed = Object.values(report.metrics || {}).flatMap((result) => result.observed_horizons_months || [])
    .filter(Number.isFinite)
  const observedRange = observed.length ? `${Math.min(...observed)}–${Math.max(...observed)} months` : 'Unavailable'
  const evaluations = [
    ['SE · internal test', report.metrics?.se?.test_by_horizon?.['12.0'], 'D'],
    ['SE · external RELS', report.metrics?.se?.external_rels?.by_horizon?.['12.0'], 'D'],
    ['AL · internal test', report.metrics?.al?.test_by_horizon?.['12.0'], 'mm'],
  ]
  return <Card title="Selectable-month forecast results" subtitle="The experimental model used by the monthly forecast controls.">
    <StatusChip label="Experimental forecast" tone="watch" />
    <p className="mt-3 text-sm text-ink-muted">Available requests: {range[0]}–{range[1]} months. Observed follow-up: {observedRange}. Unmeasured months within that range are interpolated; earlier or later requests are extrapolated. Beyond 36 months, widening ranges are heuristic and their coverage is unverified.</p>
    <div className="mt-3 overflow-x-auto"><table className="table">
      <caption className="sr-only">Selectable-month model twelve-month evaluation</caption>
      <thead><tr><th scope="col">Evaluation</th><th scope="col">12-month MAE</th><th scope="col">Within primary tolerance</th><th scope="col">Patients</th><th scope="col">Observed pairs</th></tr></thead>
      <tbody>{evaluations.map(([label, result, unit]) => <tr key={label}>
        <th scope="row">{label}</th>
        <td>{result ? `${fmt.num(result.mae, 3)} ${unit}` : 'Unavailable'}</td>
        <td>{result ? <>{fmt.pct(result.tolerance_hit_rates?.[String(result.tolerance)], 1)} within ±{fmt.num(result.tolerance, 2)} {unit}</> : 'Unavailable'}</td>
        <td>{result?.n_patients ?? 'Unavailable'}</td><td>{result?.n ?? 'Unavailable'}</td>
      </tr>)}</tbody>
    </table></div>
    <p className="note-watch mt-4">Tolerance hit rates count observed pairs within fixed error limits; they are not overall accuracy. Repeated pairs share patients. Prediction ranges describe uncertainty and do not establish 90% point accuracy. No external axial-length evaluation is available.</p>
  </Card>
}

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
    <SelectableForecastResults report={data.selectable_horizon_model} />
    <Card title="Training provenance" subtitle={`Trained on: ${data.data_source}`}>
      <StatusChip label="Exploratory research model" tone="watch" />
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
        <div><dt className="eyebrow">Independent patients</dt><dd>{metrics.n_patients}</dd></div>
        <div><dt className="eyebrow">Visits</dt><dd>{metrics.n_visits}</dd></div>
        <div><dt className="eyebrow">Training date</dt><dd>{fmt.date(data.trained_at)}</dd></div>
        <div><dt className="eyebrow">Version</dt><dd className="break-all">{data.model_version}</dd></div>
      </dl>
      <p className="mt-4 text-sm text-ink-muted">Original DIMS split: {metrics.split.strategy}. Training: {metrics.split.train_patients}; calibration: {metrics.split.val_patients}; test: {metrics.split.test_patients} patients. Expanded SE evaluations use their own patient groups.</p>
      {(data.provenance?.sources || []).map(s => <p key={s.doi} className="mt-3 text-sm">
        <a className="underline underline-offset-2" href={`https://doi.org/${s.doi}`} target="_blank" rel="noreferrer">{s.doi}</a> · {s.license}</p>)}
    </Card>
    <Card title="Fixed-horizon model results" subtitle="A high R² does not establish clinical usefulness. Lower MAE is better; compare carry-forward first.">
      <div className="overflow-x-auto"><table className="table"><caption className="sr-only">Patient-grouped model and baseline evaluation</caption>
        <thead><tr><th scope="col">Target</th><th scope="col">Test patients</th><th scope="col">Model MAE</th><th scope="col">Carry-forward MAE</th><th scope="col">Ridge MAE</th><th scope="col">RMSE</th><th scope="col">R²</th><th scope="col">Coverage</th></tr></thead>
        <tbody>{Object.entries(metrics.regression).map(([target, m]) => <tr key={target}>
          <th scope="row">{target.replace('y_', '').replace('_', ' · ')} ({target.includes('se') ? 'D' : 'mm'})</th>
          <td>{m.n_patients ?? metrics.split.test_patients}</td>
          <td>{m.mae}<span className="block text-xs text-ink-muted">95% bootstrap CI: {m.bootstrap_95ci?.mae?.join(' to ') ?? 'unavailable'}</span></td>
          <td>{m.baselines?.carry_forward?.mae ?? 'Unavailable'}</td><td>{m.baselines?.ridge?.mae ?? 'Unavailable'}</td><td>{m.rmse}</td><td>{m.r2}</td>
          <td>{fmt.num(m.interval_coverage * 100, 1)}% / nominal {fmt.num(m.nominal_coverage * 100, 0)}%</td></tr>)}</tbody></table></div>
      <p className="note-watch mt-4">Patient counts differ by prediction target; the original DIMS test split has {metrics.split.test_patients} patients. Bootstrap intervals can be unstable in small groups. R-squared and interval coverage are not prediction accuracy. These results reuse the existing benchmark and do not establish 95% overall accuracy. This model has no demonstrated clinical utility.</p>
      <Disclaimer text="Model estimates for decision support only. Not a diagnosis, prescription, medical device or causal treatment effect." />
    </Card>
    <Card title="Ablation and uncertainty">
      {Object.entries(metrics.ablation || {}).map(([name, result]) => <p key={name} className="mb-3 text-sm"><strong>{name}: </strong>
        {result.reason || `SE 12-month MAE ${result.y_se_12m?.mae ?? 'not evaluable'} D`}</p>)}
      <p className="text-sm text-ink-muted">Forecasts of change from measured values are selected using training-only patient-grouped cross-validation. Development scores after selection are not an independent evaluation. Interval calibration uses separate patients and each patient's maximum nonconformity score. Test patients are excluded from fitting and calibration; this fixed-horizon benchmark was previously reported. Legacy annual rollout bands are heuristic beyond the first year. The selectable-month model reports separate results above; its ranges beyond 36 months are heuristic and unverified.</p>
    </Card>
    <ResearchData catalog={data.research_datasets} model={data.onset_model} />
    <Card title="Limits"><ul className="list-disc space-y-2 pl-5 text-sm text-ink-muted">{data.limitations.map(x => <li key={x}>{x}</li>)}</ul></Card>
  </div>
}

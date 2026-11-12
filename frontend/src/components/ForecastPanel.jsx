import React, { useEffect, useState } from 'react'
import { fmt } from '../lib/api'
import { horizonLabel, horizonMonths } from '../lib/forecast'
import { ErrorNote, Field, Spinner, StatusChip } from './ui'
import TrajectoryChart from './TrajectoryChart'

const PRESETS = [1, 6, 12, 24, 36, 60]
const SUPPORT_LABELS = {
  observed_horizon: 'Observed training horizon',
  interpolated_horizon: 'Interpolated forecast',
  extrapolated_horizon: 'Extrapolated forecast',
}

function ForecastValue({ estimate, measure }) {
  const isSE = measure === 'se'
  const format = isSE ? fmt.dioptre : fmt.mm
  const minimum = estimate?.support?.training_min_horizon_months
  const maximum = estimate?.support?.training_max_horizon_months
  return <div className="card-quiet px-4 py-3">
    <h3 className="eyebrow">{isSE ? 'Spherical equivalent' : 'Axial length'}</h3>
    {estimate ? <>
      <p className="stat mt-1 text-xl font-semibold">{format(estimate.value)} {isSE ? 'D' : 'mm'}</p>
      <p className="mt-1 text-xs text-ink-muted">{estimate.interval_label || 'Estimated range'}: {format(estimate.lower)} to {format(estimate.upper)} {isSE ? 'D' : 'mm'}</p>
      {estimate.support?.status && <div className="mt-2"><StatusChip
        label={SUPPORT_LABELS[estimate.support.status] || estimate.support.status}
        tone={estimate.support.status === 'extrapolated_horizon' ? 'watch' : 'neutral'} /></div>}
      {estimate.support?.status === 'extrapolated_horizon' && <p className="mt-1 text-xs text-ink-muted">
        {minimum && maximum ? `Outside measured follow-up range of ${minimum}–${maximum} months` : `Beyond measured follow-up${maximum ? ` of ${maximum} months` : ''}`}; accuracy at this horizon has not been established.
      </p>}
    </> : <p className="mt-2 text-sm text-ink-muted">Unavailable for this record.</p>}
  </div>
}

/** Read-only forecasts. Each response belongs to one record version and horizon. */
export default function ForecastPanel({ history, loadPrediction, recordKey }) {
  const [months, setMonths] = useState(12)
  const [draft, setDraft] = useState('12')
  const [unit, setUnit] = useState('months')
  const [validation, setValidation] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(true)
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let alive = true
    setBusy(true); setError(null); setResult(null)
    Promise.resolve().then(() => loadPrediction(months, { signal: controller.signal }))
      .then((prediction) => {
        if (!alive) return
        if (!prediction?.horizons?.[`${months}m`]) throw new Error('The server did not return the selected forecast horizon. Try again.')
        setResult({ months, recordKey, prediction })
      })
      .catch((err) => { if (alive && err.name !== 'AbortError') setError(err) })
      .finally(() => { if (alive) setBusy(false) })
    return () => { alive = false; controller.abort() }
  }, [months, recordKey, loadPrediction, retry])

  const current = result?.months === months && result?.recordKey === recordKey ? result.prediction : null
  const selected = current?.horizons?.[`${months}m`]
  const select = (value) => {
    setMonths(value); setDraft(String(value)); setUnit('months'); setValidation(null)
  }
  function submit(event) {
    event.preventDefault()
    const value = horizonMonths(draft, unit)
    if (value === null) { setValidation('Choose 1–120 whole months, or the equivalent in years (up to 10 years).'); return }
    setValidation(null); setMonths(value)
  }
  function changeUnit(value) {
    const converted = horizonMonths(draft, unit) ?? months
    setUnit(value)
    setDraft(String(value === 'years' ? converted / 12 : converted))
    setValidation(null)
  }

  return <div className="space-y-4">
    <div className="space-y-1">
      <StatusChip label="Experimental forecast" tone="watch" />
      <p className="text-xs text-ink-muted">Estimated ranges describe uncertainty; they do not mean 90% prediction accuracy.</p>
    </div>
    <form onSubmit={submit} noValidate className="flex flex-wrap items-end gap-3">
      <div className="w-36"><Field label="Forecast horizon" error={validation}>
        <input className="input" type="number" inputMode="decimal" min={unit === 'years' ? 1 / 12 : 1}
          max={unit === 'years' ? 10 : 120} step="any" value={draft} aria-invalid={!!validation}
          onChange={(event) => { setDraft(event.target.value); setValidation(null) }} />
      </Field></div>
      <div className="w-32"><Field label="Time unit"><select className="input" value={unit}
        onChange={(event) => changeUnit(event.target.value)}><option value="months">Months</option><option value="years">Years</option></select></Field></div>
      <button className="btn-primary" type="submit">Calculate forecast</button>
    </form>
    <div className="flex flex-wrap gap-2" aria-label="Forecast presets">
      {PRESETS.map((value) => <button key={value} type="button" onClick={() => select(value)}
        aria-pressed={value === months} className={`btn btn-sm ${value === months ? 'btn-primary' : 'btn-secondary'}`}>
        {value < 12 ? `${value} mo` : `${value / 12} yr`}</button>)}
    </div>
    <p className="text-sm text-ink-muted">Forecast for {horizonLabel(months)} after the latest observation. Longer forecasts carry greater uncertainty.</p>
    <ErrorNote error={error} onRetry={() => setRetry((value) => value + 1)} />
    {!current && !error && <div role="status"><Spinner label={`Calculating ${horizonLabel(months)} forecast`} /></div>}
    {selected && !busy && <div className="space-y-4" aria-live="polite">
      <div className="grid gap-3 sm:grid-cols-2"><ForecastValue estimate={selected.se} measure="se" /><ForecastValue estimate={selected.al} measure="al" /></div>
      <div className="grid min-w-0 grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="min-w-0"><h3 className="mb-2 text-sm font-medium">Spherical equivalent</h3><TrajectoryChart history={history} prediction={current} measure="se" height={280} /></div>
        <div className="min-w-0"><h3 className="mb-2 text-sm font-medium">Axial length</h3><TrajectoryChart history={history} prediction={current} measure="al" height={280} /></div>
      </div>
      {current.warnings?.length > 0 && <ul className="list-disc space-y-1 pl-5 text-xs text-ink-muted">{current.warnings.map((warning, index) => <li key={`${index}-${warning}`}>{warning}</li>)}</ul>}
      {current.model_version && <p className="text-xs text-ink-faint">Model: {current.model_version}</p>}
    </div>}
  </div>
}

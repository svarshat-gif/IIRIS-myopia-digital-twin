/** Measured history and dynamic forecasts on a true numeric month axis. */
import React, { useMemo } from 'react'
import { Line } from 'react-chartjs-2'
import { C, baseOptions } from '../lib/charts'
import { fmt } from '../lib/api'
import { observedTimeline, sortedHorizons } from '../lib/forecast'

export function trajectoryData(history, prediction, scenario, measure) {
  const { points, anchor } = observedTimeline(history, measure)
  const future = sortedHorizons(prediction).filter((entry) => entry[measure])
  if (!points.length && !future.length) return null
  const scenarioHorizons = sortedHorizons(scenario)
  const forecast = (field, source = future) => [
    ...(anchor ? [anchor] : []),
    ...source.map((entry) => ({ x: entry.horizon_months, y: entry[measure]?.[field] ?? null })),
  ]
  const labels = new Set(future.map((entry) => entry[measure].interval_label).filter(Boolean))
  const rangeLabel = labels.size === 1 ? [...labels][0] : 'Estimated range'
  const datasets = [
    { label: rangeLabel, data: forecast('upper'), borderColor: 'transparent',
      backgroundColor: C.band, pointRadius: 0, fill: '+1', tension: 0, order: 5 },
    { label: '_lower', data: forecast('lower'), borderColor: 'transparent',
      pointRadius: 0, fill: false, tension: 0, order: 5 },
    { label: 'Your results', data: points,
      borderColor: C.observed, backgroundColor: C.observed, borderWidth: 2.2,
      pointRadius: 3.4, pointHoverRadius: 6, pointBackgroundColor: '#fff',
      pointBorderWidth: 2, tension: 0, order: 1 },
    { label: 'Expected', data: forecast('value'),
      borderColor: C.predicted, backgroundColor: C.predicted, borderWidth: 2.2,
      borderDash: [6, 4], pointRadius: future.length > 12 ? 0 : 4,
      pointHoverRadius: 5, pointBackgroundColor: '#fff', pointBorderWidth: 2,
      tension: 0, order: 2 },
  ]
  if (scenarioHorizons.some((entry) => entry[measure])) {
    datasets.push({ label: 'If you change things', data: forecast('value', scenarioHorizons),
      borderColor: C.scenario, backgroundColor: C.scenario, borderWidth: 2.2,
      borderDash: [2, 3], pointRadius: 4, pointBackgroundColor: '#fff',
      pointBorderWidth: 2, tension: 0, order: 3 })
  }
  return { datasets }
}

export default function TrajectoryChart({ history, prediction, scenario = null, measure = 'se', height = 300 }) {
  const data = useMemo(() => trajectoryData(history, prediction, scenario, measure),
    [history, prediction, scenario, measure])
  if (!data) return <p className="py-10 text-center text-sm text-ink-muted">
    Add an eye test result to see this trajectory.</p>
  const unit = measure === 'se' ? ' D' : ' mm'
  const opts = baseOptions({ yTitle: measure === 'se' ? 'Prescription (D)' : 'Eye length (mm)',
    xTitle: 'Months from latest observation', reverseY: measure === 'se' })
  opts.scales.x.type = 'linear'
  opts.scales.x.ticks.callback = (value) => `${Number(value.toFixed(1))}`
  opts.interaction = { mode: 'nearest', axis: 'x', intersect: false }
  opts.plugins.tooltip.callbacks = {
    title: (items) => {
      const month = items[0]?.parsed.x
      return month === 0 ? 'Latest observation' : month > 0
        ? `${fmt.num(month, month % 1 ? 1 : 0)} months ahead`
        : `${fmt.num(-month, month % 1 ? 1 : 0)} months before latest observation`
    },
    label: (ctx) => ctx.parsed.y === null ? null : `${ctx.dataset.label}: ${fmt.num(ctx.parsed.y, 2)}${unit}`,
  }
  return <div style={{ height, position: 'relative', minWidth: 0, width: '100%' }}><Line data={data} options={opts} role="img"
    aria-label={`${measure === 'se' ? 'Spherical equivalent' : 'Axial length'} measured history, forecast and estimated range by month`} /></div>
}

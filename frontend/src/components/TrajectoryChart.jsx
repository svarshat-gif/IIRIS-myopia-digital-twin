/**
 * Observed history + forecast with the uncertainty band, optionally overlaid
 * with a scenario. The band is two invisible datasets filled between, so the
 * interval reads as an area rather than three competing lines.
 */
import React, { useMemo } from 'react'
import { Line } from 'react-chartjs-2'
import { C, baseOptions } from '../lib/charts'
import { fmt } from '../lib/api'

function addMonths(d, months) {
  const out = new Date(d)
  out.setMonth(out.getMonth() + months)
  return out
}
const short = (d) => d.toLocaleDateString(undefined, { month: 'short', year: '2-digit' })

export default function TrajectoryChart({
  history, prediction, scenario = null, measure = 'se', height = 300,
}) {
  const data = useMemo(() => {
    if (!history?.length) return null
    const key = measure === 'se' ? 'spherical_equivalent' : 'axial_length'
    const observed = history
      .map((h) => ({ date: new Date(`${h.visit_date}T00:00:00`), value: h[key], month: h.followup_month }))
      .filter((p) => p.value !== null && p.value !== undefined)
    if (!observed.length) return null

    const last = observed[observed.length - 1]
    const future = ['6m', '12m'].map((h) => {
      const e = prediction?.horizons?.[h]?.[measure]
      if (!e) return null
      return { label: `+${h}`, date: addMonths(last.date, h === '6m' ? 6 : 12), ...e,
               scenario: scenario?.horizons?.[h]?.[measure] || null }
    }).filter(Boolean)

    const labels = [...observed.map((p) => Number.isNaN(p.date.getTime()) ? `Month ${p.month}` : short(p.date)),
                    ...future.map((f) => Number.isNaN(f.date.getTime()) ? f.label : short(f.date))]
    const anchor = observed.length - 1
    const pad = observed.map(() => null)
    // Anchoring the forecast on the last observed point keeps the line continuous.
    const withAnchor = (vals) => {
      const arr = [...pad, ...vals]
      arr[anchor] = last.value
      return arr
    }

    const datasets = [
      { label: '90% range', data: withAnchor(future.map((f) => f.upper)),
        borderColor: 'transparent', backgroundColor: C.band, pointRadius: 0,
        fill: '+1', tension: 0.3, order: 5 },
      { label: '_lower', data: withAnchor(future.map((f) => f.lower)),
        borderColor: 'transparent', pointRadius: 0, fill: false, tension: 0.3, order: 5 },
      { label: 'Your results',
        data: [...observed.map((p) => p.value), ...future.map(() => null)],
        borderColor: C.observed, backgroundColor: C.observed, borderWidth: 2.2,
        pointRadius: 3.4, pointHoverRadius: 6, pointBackgroundColor: '#fff',
        pointBorderWidth: 2, tension: 0.25, order: 1 },
      { label: 'Expected', data: withAnchor(future.map((f) => f.value)),
        borderColor: C.predicted, backgroundColor: C.predicted, borderWidth: 2.2,
        borderDash: [6, 4], pointRadius: 4, pointBackgroundColor: '#fff',
        pointBorderWidth: 2, tension: 0.3, order: 2 },
    ]

    if (scenario && future.some((f) => f.scenario)) {
      datasets.push({
        label: 'If you change things',
        data: withAnchor(future.map((f) => f.scenario?.value ?? null)),
        borderColor: C.scenario, backgroundColor: C.scenario, borderWidth: 2.2,
        borderDash: [2, 3], pointRadius: 4, pointBackgroundColor: '#fff',
        pointBorderWidth: 2, tension: 0.3, order: 3,
      })
    }
    return { labels, datasets }
  }, [history, prediction, scenario, measure])

  if (!data) {
    return <p className="py-10 text-center text-sm text-ink-muted">
      Add at least one eye test result to see your trajectory.</p>
  }

  const unit = measure === 'se' ? ' D' : ' mm'
  const opts = baseOptions({
    yTitle: measure === 'se' ? 'Prescription (D)' : 'Eye length (mm)',
    // More negative = more short-sighted. Reversing puts "worse" lower down,
    // which is how a progression chart is normally read.
    reverseY: measure === 'se',
  })
  opts.plugins.tooltip.callbacks = {
    label: (ctx) => ctx.parsed.y === null ? null
      : `${ctx.dataset.label}: ${fmt.num(ctx.parsed.y, 2)}${unit}`,
  }

  return <div style={{ height }}><Line data={data} options={opts} role="img" aria-label="Observed trajectory with model estimate and prediction interval" /></div>
}

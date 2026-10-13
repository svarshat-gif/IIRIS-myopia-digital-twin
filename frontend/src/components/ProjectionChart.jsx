/**
 * Multi-year projection: measured history, then the modelled years ahead with a
 * band that widens as confidence drops. An optional scenario line overlays it.
 */
import React, { useMemo } from 'react'
import { Line } from 'react-chartjs-2'
import { C, baseOptions } from '../lib/charts'
import { fmt } from '../lib/api'

const yr = (s) => new Date(`${s}T00:00:00`).getFullYear()

export default function ProjectionChart({
  history = [], baseline, scenario = null, measure = 'se', height = 320,
}) {
  const data = useMemo(() => {
    if (!baseline?.points?.length) return null
    const key = measure === 'se' ? 'spherical_equivalent' : 'axial_length'
    const lo = measure === 'se' ? 'se_lower' : 'al_lower'
    const hi = measure === 'se' ? 'se_upper' : 'al_upper'

    const observed = history
      .map((h) => ({ label: h.visit_date ? fmt.monthYear(h.visit_date) : `Month ${h.followup_month}`, value: h[key] }))
      .filter((p) => p.value !== null && p.value !== undefined)

    const labels = [...observed.map((o) => o.label),
                    ...baseline.points.map((p) => p.date ? `${yr(p.date)}` : `Month ${p.followup_month}`)]
    const anchor = Math.max(0, observed.length - 1)
    const pad = observed.map(() => null)
    const withAnchor = (vals, anchorValue) => {
      const arr = [...pad, ...vals]
      if (observed.length) arr[anchor] = anchorValue
      return arr
    }
    const startValue = observed.length
      ? observed[observed.length - 1].value : baseline.start[key]

    const datasets = [
      { label: 'Likely range', data: withAnchor(baseline.points.map((p) => p[hi]),
                                                startValue),
        borderColor: 'transparent', backgroundColor: C.band, pointRadius: 0,
        fill: '+1', tension: 0.35, order: 6 },
      { label: '_lower', data: withAnchor(baseline.points.map((p) => p[lo]), startValue),
        borderColor: 'transparent', pointRadius: 0, fill: false, tension: 0.35, order: 6 },
    ]

    if (observed.length) {
      datasets.push({
        label: 'Measured',
        data: [...observed.map((o) => o.value), ...baseline.points.map(() => null)],
        borderColor: C.observed, backgroundColor: C.observed, borderWidth: 2.2,
        pointRadius: 3.4, pointHoverRadius: 6, pointBackgroundColor: '#fff',
        pointBorderWidth: 2, tension: 0.25, order: 1,
      })
    }

    datasets.push({
      label: observed.length ? 'If nothing changes' : 'Projection',
      data: withAnchor(baseline.points.map((p) => p[key]), startValue),
      borderColor: C.predicted, backgroundColor: C.predicted, borderWidth: 2.4,
      borderDash: [6, 4], pointRadius: 3.6, pointBackgroundColor: '#fff',
      pointBorderWidth: 2, tension: 0.35, order: 2,
    })

    if (scenario?.points?.length) {
      datasets.push({
        label: 'With the changes',
        data: withAnchor(scenario.points.map((p) => p[key]), startValue),
        borderColor: C.scenario, backgroundColor: C.scenario, borderWidth: 2.4,
        pointRadius: 3.6, pointBackgroundColor: '#fff', pointBorderWidth: 2,
        tension: 0.35, order: 3,
      })
    }
    return { labels, datasets }
  }, [history, baseline, scenario, measure])

  if (!data) return null

  const unit = measure === 'se' ? ' D' : ' mm'
  const opts = baseOptions({
    yTitle: measure === 'se' ? 'Prescription (D)' : 'Eye length (mm)',
    reverseY: measure === 'se',
  })
  opts.plugins.tooltip.callbacks = {
    label: (ctx) => ctx.parsed.y === null ? null
      : `${ctx.dataset.label}: ${fmt.num(ctx.parsed.y, 2)}${unit}`,
    afterBody: (items) => {
      const i = items[0]?.dataIndex ?? 0
      const offset = i - (data.labels.length - baseline.points.length)
      const p = baseline.points[offset]
      return p ? `Confidence: ${p.confidence}` : ''
    },
  }

  return <div style={{ height }}><Line data={data} options={opts} /></div>
}

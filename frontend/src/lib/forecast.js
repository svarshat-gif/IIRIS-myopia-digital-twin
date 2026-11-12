/** Forecast horizons are numeric months; object-key ordering is not chronological. */
export function sortedHorizons(prediction) {
  return Object.entries(prediction?.horizons || {})
    .map(([key, value]) => ({ key, ...value,
      horizon_months: value.horizon_months ?? (/^\d+m$/.test(key) ? Number(key.slice(0, -1)) : NaN),
    }))
    .filter((entry) => Number.isFinite(entry.horizon_months) && entry.horizon_months > 0)
    .sort((a, b) => a.horizon_months - b.horizon_months)
}

export function horizonMonths(value, unit = 'months') {
  if (value === '' || value === null || value === undefined) return null
  const months = Number(value) * (unit === 'years' ? 12 : 1)
  const rounded = Math.round(months)
  return Number.isFinite(months) && Math.abs(months - rounded) < 1e-8 && rounded >= 1 && rounded <= 120
    ? rounded : null
}

export function horizonLabel(months) {
  return months >= 12 && months % 12 === 0
    ? `${months / 12} year${months === 12 ? '' : 's'} (${months} months)`
    : `${months} month${months === 1 ? '' : 's'}`
}

const finite = (value) => typeof value === 'number' && Number.isFinite(value)
function visitDate(value) {
  if (!value || typeof value !== 'string') return null
  const parsed = new Date(value.length === 10 ? `${value}T00:00:00` : value)
  return Number.isNaN(parsed.getTime()) ? null : parsed.getTime()
}

/** Use recorded elapsed months or real dates, never a fabricated calendar date. */
export function observedTimeline(history = [], measure = 'se') {
  if (!history.length) return { points: [], anchor: null }
  const key = measure === 'se' ? 'spherical_equivalent' : 'axial_length'
  const allMonths = history.every((visit) => finite(visit.followup_month))
  const allDates = history.every((visit) => visitDate(visit.visit_date) !== null)
  const time = (visit) => allMonths ? visit.followup_month : visitDate(visit.visit_date)
  const sorted = allMonths || allDates ? [...history].sort((a, b) => time(a) - time(b)) : history
  const latest = sorted.at(-1)
  const latestDate = visitDate(latest.visit_date)
  const xFor = (visit) => {
    if (finite(latest.followup_month) && finite(visit.followup_month)) return visit.followup_month - latest.followup_month
    const date = visitDate(visit.visit_date)
    if (latestDate !== null && date !== null) return (date - latestDate) / (365.25 / 12 * 86400000)
    return visit === latest ? 0 : null
  }
  const points = sorted.map((visit) => ({ x: xFor(visit), y: visit[key] }))
    .filter((point) => finite(point.x) && finite(point.y)).sort((a, b) => a.x - b.x)
  return { points, anchor: finite(latest[key]) ? { x: 0, y: latest[key] } : null }
}

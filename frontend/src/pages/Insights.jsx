/** Why the model says what it says, plus the record's version history. */
import React, { useEffect, useState } from 'react'
import { Bar } from 'react-chartjs-2'
import { api, fmt } from '../lib/api'
import { C, baseOptions } from '../lib/charts'
import {
  Card, Collapsible, Disclaimer, ErrorNote, SkeletonCard, Spinner, StatusChip,
  toneForBand,
} from '../components/ui'

const TARGETS = [
  ['se_12m', 'Prescription in 12 months'], ['se_6m', 'Prescription in 6 months'],
  ['al_12m', 'Eye length in 12 months'], ['al_6m', 'Eye length in 6 months'],
]

export default function Insights() {
  const [target, setTarget] = useState('se_12m')
  const [data, setData] = useState(null)
  const [versions, setVersions] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    setLoading(true); setError(null)
    Promise.all([api.explanation(target), api.versions()])
      .then(([e, v]) => { if (!alive) return; setData(e); setVersions(v.versions) })
      .catch((e) => alive && setError(e))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [target])

  if (loading && !data) return <div className="space-y-4">
    <div className="skeleton h-10 w-56" /><SkeletonCard lines={6} /></div>
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const rows = [...data.contributions].reverse()

  return (
    <div className="space-y-5">
      <div>
        <p className="script text-2xl text-ink-muted">the reasoning</p>
        <h1 className="text-3xl font-semibold">Insights</h1>
      </div>

      <Card
        title="What is pushing your estimate"
        subtitle="Bars to the right push toward less short-sightedness; to the left, more."
        actions={
          <select className="input w-auto text-[13px]" value={target}
                  onChange={(e) => setTarget(e.target.value)}>
            {TARGETS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        }
      >
        {loading ? <Spinner label="Working out the contributions" /> : (
          <>
            <div style={{ height: Math.max(240, rows.length * 34) }}>
              <Bar
                data={{
                  labels: rows.map((c) => c.label),
                  datasets: [{
                    label: 'Contribution',
                    data: rows.map((c) => c.contribution),
                    backgroundColor: rows.map((c) =>
                      c.contribution >= 0 ? C.positive : C.negative),
                    borderRadius: 4, barThickness: 16,
                  }],
                }}
                options={{
                  ...baseOptions(),
                  indexAxis: 'y',
                  plugins: {
                    ...baseOptions().plugins,
                    legend: { display: false },
                    tooltip: {
                      ...baseOptions().plugins.tooltip,
                      callbacks: {
                        afterLabel: (ctx) => {
                          const c = rows[ctx.dataIndex]
                          return c.missing ? 'you have not recorded this'
                                           : `your value: ${c.value}`
                        },
                      },
                    },
                  },
                  scales: {
                    x: { ...baseOptions().scales.x,
                         title: { display: true, text: 'Effect on the estimate' } },
                    y: { ...baseOptions().scales.y, ticks: { autoSkip: false } },
                  },
                }}
              />
            </div>

            <div className="mt-5 space-y-2.5">
              {data.plain_language.map((line, i) => (
                <p key={i} className="flex gap-2.5 text-[13.5px] leading-relaxed">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-sand-500" />
                  {line}
                </p>
              ))}
            </div>

            <div className="mt-4 note-watch">
              <strong className="font-semibold">This explains the model, not your eyes. </strong>
              {data.attribution_disclaimer}
            </div>
            <Collapsible label="How this was worked out">
              <p className="text-[12.5px] leading-relaxed text-ink-muted">
                {data.method_note} Method: <code
                  className="rounded bg-sand-200 px-1.5 py-0.5">{data.method}</code>,
                model <code className="rounded bg-sand-200 px-1.5 py-0.5">
                  {data.model_version}</code>.
              </p>
            </Collapsible>
            <Disclaimer text={data.disclaimer} />
          </>
        )}
      </Card>

      {versions?.length > 0 && (
        <Card title="How your record has grown"
              subtitle="Every result you add saves a new version. Nothing is overwritten.">
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th>Version</th><th>From the visit on</th><th>Prescription</th>
                  <th>Eye length</th><th>Expected in 12m</th><th>Risk</th>
                </tr>
              </thead>
              <tbody>
                {[...versions].reverse().map((v) => (
                  <tr key={v.version}>
                    <td className="font-medium">v{v.version}</td>
                    <td>{fmt.date(v.latest_visit)}</td>
                    <td className="stat">{fmt.dioptre(v.spherical_equivalent)} D</td>
                    <td className="stat">{fmt.mm(v.axial_length)} mm</td>
                    <td className="stat text-ink-muted">
                      {fmt.dioptre(v.predicted_se_12m)} D</td>
                    <td>{v.risk_band
                      ? <StatusChip label={v.risk_band} tone={toneForBand(v.risk_band)} />
                      : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-[12.5px] leading-relaxed text-ink-faint">
            Because each version is kept, you can always see what Iiris expected before
            your latest test — and whether it turned out to be right.
          </p>
        </Card>
      )}
    </div>
  )
}

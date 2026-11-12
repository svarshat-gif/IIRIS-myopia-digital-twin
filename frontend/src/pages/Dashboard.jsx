import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, fmt, seDirection } from '../lib/api'
import {
  AnimatedNumber, Card, Disclaimer, EmptyState, ErrorNote, SkeletonCard, Stat,
  StatusChip, Tip, toneForBand, toneForCategory,
} from '../components/ui'
import ForecastPanel from '../components/ForecastPanel'

/** Two results a few days apart must not read as "over 0 months". */
function intervalLabel(change) {
  const days = change.days ?? Math.round((change.months || 0) * 30.4)
  if (days <= 1) return 'since the previous result'
  if (days < 45) return `over ${days} days`
  return `over ${change.months} months`
}

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
}

export default function Dashboard() {
  const [summary, setSummary] = useState(null)
  const [twin, setTwin] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const loadForecast = useCallback((months, options) => api.prediction(months, options), [])

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const s = await api.summary()
      setSummary(s)
      if (s.has_record) setTwin(await api.twin())
    } catch (e) { setError(e) } finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="skeleton h-10 w-64" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-24" />)}
        </div>
        <SkeletonCard lines={5} />
      </div>
    )
  }
  if (error) return <ErrorNote error={error} onRetry={load} />
  if (!summary) return null

  const firstName = (summary.user.full_name || '').split(' ')[0]

  /* ---------------------------------------------- empty state (new account) */
  if (!summary.has_record) {
    return (
      <div className="space-y-5">
        <div>
          <p className="script text-2xl text-ink-muted">{greeting()},</p>
          <h1 className="text-3xl font-semibold">{firstName}</h1>
        </div>
        <Card>
          <EmptyState
            icon={<svg width="44" height="44" viewBox="0 0 24 24" fill="none"
                       stroke="currentColor" strokeWidth="1.2" aria-hidden="true">
              <ellipse cx="12" cy="12" rx="10" ry="6.5" /><circle cx="12" cy="12" r="3" />
            </svg>}
            title="Let's start your record"
            action={<Link to="/app/records?add=1" className="btn-primary">
              Add my first result</Link>}
          >
            Add the results from your most recent eye test. You need your prescription;
            everything else is optional. As soon as there is one entry, Iiris can start
            showing you where things are heading.
          </EmptyState>
        </Card>
        <Card title="No results to hand?"
              subtitle="Try the simulator with rough numbers instead.">
          <p className="lede text-sm">
            The simulator works from an age and a prescription alone. It is a good way
            to see what Iiris does before your next appointment.
          </p>
          <Link to="/app/simulator" className="btn-secondary btn-sm mt-4">
            Open the simulator
          </Link>
        </Card>
      </div>
    )
  }

  /* ---------------------------------------------------------- normal state */
  const { latest, change_since_previous: change, prediction, category,
          derived, next_appointment: next } = summary
  const risk = prediction?.risk
  const trend = derived?.se_slope_per_year

  return (
    <div className="space-y-5">
      {/* -------- header -------- */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="script text-2xl text-ink-muted">{greeting()},</p>
          <h1 className="text-3xl font-semibold">{firstName}</h1>
        </div>
        <div className="flex items-center gap-2">
          <StatusChip label={category?.label} tone={toneForCategory(category?.label)} />
          <StatusChip label={`Record v${summary.twin_version}`} tone="outline" />
        </div>
      </div>

      {/* -------- headline stats -------- */}
      <div className="grid gap-3 stagger sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Your prescription"
          hint="Spherical equivalent, in dioptres. A more negative number means more short-sighted."
          value={<AnimatedNumber value={latest.spherical_equivalent} digits={2} signed />}
          unit="D"
          sub={`measured ${fmt.date(latest.visit_date)}`}
        />
        <Stat
          label="Eye length"
          hint="Axial length: how long the eye is, front to back. It grows as short-sightedness increases."
          value={<AnimatedNumber value={latest.axial_length} digits={2} />}
          unit="mm"
          sub={`${summary.n_visits} results on record`}
        />
        <Stat
          label="Change last visit"
          value={change ? <AnimatedNumber value={change.spherical_equivalent}
                                          digits={2} signed /> : '—'}
          unit={change ? 'D' : ''}
          tone={!change ? 'default'
            : change.spherical_equivalent <= -0.5 ? 'alert'
            : change.spherical_equivalent <= -0.25 ? 'watch'
            // Still getting worse, just slowly -- neutral, never green.
            : change.spherical_equivalent < -0.05 ? 'default' : 'calm'}
          sub={change
            ? `${seDirection(change.spherical_equivalent)}, ${intervalLabel(change)}`
            : 'Add a second result to see change'}
        />
        <Stat
          label="Yearly pace"
          hint="How fast your prescription has been changing recently, in dioptres per year."
          value={trend === null || trend === undefined
            ? '—' : <AnimatedNumber value={trend} digits={2} signed />}
          unit="D/yr"
          tone={trend < -0.5 ? 'alert' : trend < -0.25 ? 'watch'
            : trend < -0.05 ? 'default' : 'calm'}
          sub={trend < -0.5 ? 'Faster than typical' :
               trend < -0.25 ? 'Moderate pace' :
               trend < -0.05 ? 'Slow' : 'Holding steady'}
        />
      </div>

      {/* -------- chart -------- */}
      <Card
        title="Where things are heading"
        subtitle="Your measured results, and what the model expects next."
      >
        {twin && <ForecastPanel history={twin.history} loadPrediction={loadForecast} recordKey={`me:${summary.twin_version}`} />}

        {risk && (
          <div className="mt-5">
            <div className="card-quiet px-4 py-3">
              <div className="flex items-center gap-1.5">
                <span className="eyebrow">Chance of a fast year (12 months)</span>
                <Tip text="The model's estimated probability that your prescription changes by 0.50 D or more over the next 12 months." />
              </div>
              <div className="mt-1 flex items-center gap-2">
                <span className="stat text-xl font-semibold">{fmt.pct(risk?.probability)}</span>
                <StatusChip label={risk?.band} tone={toneForBand(risk?.band)} />
              </div>
              <div className="mt-0.5 text-[12px] text-ink-muted">
                a change of 0.50 D or more
              </div>
            </div>
          </div>
        )}

        {risk?.consistent_with_interval === false && (
          <div className="mt-3 note-watch">
            <strong className="font-semibold">Two estimates disagree here. </strong>
            {risk.consistency_note} The range above is the more reliable of the two.
          </div>
        )}
        <Disclaimer text={summary.disclaimer} />
      </Card>

      {/* -------- next steps -------- */}
      <div className="grid gap-4 stagger lg:grid-cols-3">
        <Card title="Next appointment">
          {next ? (
            <>
              <p className="text-2xl font-semibold">{fmt.date(next.scheduled_for)}</p>
              <p className="mt-1 text-[13px] text-ink-muted">
                {fmt.relative(next.days_away)}{next.time_label && ` · ${next.time_label}`}
              </p>
              <div className="mt-4 space-y-1 text-[13px]">
                {next.clinic && <p className="font-medium">{next.clinic}</p>}
                {next.practitioner && <p className="text-ink-muted">{next.practitioner}</p>}
                {next.reason && <p className="text-ink-muted">{next.reason}</p>}
              </div>
              <Link to="/app/appointments" className="btn btn-ghost btn-sm mt-4 -ml-2">
                All appointments →
              </Link>
            </>
          ) : (
            <>
              <p className="lede text-sm">
                Nothing booked. Most children having their myopia monitored are seen
                every six months — ask your optometrist what is right for you.
              </p>
              <Link to="/app/appointments?add=1" className="btn-secondary btn-sm mt-4">
                Add an appointment
              </Link>
            </>
          )}
        </Card>

        <Card title="Try a different future">
          <p className="lede text-sm">
            See what the model expects if your habits change — more time outdoors, less
            time up close, longer breaks.
          </p>
          <Link to="/app/simulator" className="btn-primary btn-sm mt-4">
            Open the simulator
          </Link>
        </Card>

        <Card title="Add a new result">
          <p className="lede text-sm">
            Been for a test? Add the numbers and Iiris will update your trend and your
            projection straight away.
          </p>
          <Link to="/app/records?add=1" className="btn-secondary btn-sm mt-4">
            Add a result
          </Link>
        </Card>
      </div>

      {summary.data_completeness && (
        <Card title="How complete your record is"
              subtitle="Blank fields stay blank — Iiris never fills one in with a guess.">
          <div className="grid gap-4 sm:grid-cols-3">
            {[['Eye measurements', summary.data_completeness.clinical],
              ['Daily habits', summary.data_completeness.behaviour],
              ['Screen setup', summary.data_completeness.ergonomics]].map(([l, v]) => (
              <div key={l}>
                <div className="flex items-baseline justify-between text-[13px]">
                  <span className="text-ink-muted">{l}</span>
                  <span className="stat font-semibold">{Math.round((v || 0) * 100)}%</span>
                </div>
                <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-sand-300">
                  <div className="h-full rounded-full bg-ink transition-all duration-700"
                       style={{ width: `${Math.round((v || 0) * 100)}%` }} />
                </div>
              </div>
            ))}
          </div>
          <p className="mt-4 text-[12.5px] leading-relaxed text-ink-faint">
            The more of the habit and screen-setup fields you fill in, the more the
            simulator has to work with. It still works without them.
          </p>
        </Card>
      )}
    </div>
  )
}

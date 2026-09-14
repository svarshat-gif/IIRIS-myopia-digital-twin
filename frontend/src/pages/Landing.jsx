import Logo from '../components/Logo'
import React, { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { installScrollReveal } from '../lib/interactions'


const STEPS = [
  { n: '01', title: 'Add your results',
    body: 'Type in what your optometrist measured — your prescription, and the eye length scan if you have it. Anything you do not have, you leave blank.' },
  { n: '02', title: 'Watch the trend',
    body: 'Iiris keeps every visit and draws the line between them, so you can see whether things are moving quickly, slowly, or holding steady.' },
  { n: '03', title: 'Try a different future',
    body: 'Change the habits — more time outdoors, a longer arm on the screen — and see how the modelled trajectory shifts.' },
]

const FEATURES = [
  { title: 'Your whole history, in one place',
    body: 'Every appointment and every measurement, kept together instead of scattered across prescription slips.',
    icon: IconStack },
  { title: 'A forecast that admits doubt',
    body: 'Every projection comes with a range, not a single confident number. The range widens the further out you look — because it should.',
    icon: IconRange },
  { title: 'Reasons, not just results',
    body: 'Iiris shows which of your habits and measurements moved the estimate, in plain words.',
    icon: IconWhy },
  { title: 'Appointments you will not miss',
    body: 'Keep your past visits and your next review in the same place as the numbers they produced.',
    icon: IconBell },
]

export default function Landing() {
  useEffect(() => installScrollReveal(), [])
  return (
    <div className="relative min-h-screen overflow-hidden">
      {/* ------------------------------------------------ nav */}
      <header className="relative z-10 mx-auto flex max-w-6xl items-center
                         justify-between px-5 py-6">
        <Logo />
        <nav className="flex items-center gap-2">
          <Link to="/try" className="btn btn-ghost btn-sm hidden sm:inline-flex">
            Try the simulator
          </Link>
          <Link to="/login" className="btn btn-secondary btn-sm">Sign in</Link>
          <Link to="/signup" className="btn-primary btn-sm">Get started</Link>
        </nav>
      </header>

      {/* ------------------------------------------------ hero */}
      <section className="relative mx-auto max-w-6xl px-5 pb-20 pt-10 sm:pt-16">
        <div className="grid items-center gap-12 lg:grid-cols-[1.05fr_.95fr]">
          <div className="animate-fade-up">
            <Logo size="xl" showWordmark={false}
                  className="mb-4 text-ink cursor-pointer" />
            <p className="script text-2xl text-ink-muted">your eyes, over time</p>
            <h1 className="mt-3 text-[42px] font-semibold leading-[1.05] sm:text-[56px]">
              See how your
              <span className="relative mx-3 inline-block">
                <span className="relative z-10">short-sightedness</span>
                <svg className="absolute -bottom-1 left-0 z-0 w-full" height="12"
                     viewBox="0 0 300 12" preserveAspectRatio="none" aria-hidden="true">
                  <path d="M2 8c60-6 130-7 296-3" stroke="#DDD3C1" strokeWidth="6"
                        fill="none" strokeLinecap="round" />
                </svg>
              </span>
              is actually changing.
            </h1>
            <p className="lede mt-6 max-w-xl text-[17px]">
              A prescription tells you where your eyes are today. Iiris keeps every
              reading you have ever had, shows you the direction of travel, and lets you
              test what a different set of habits might do to it.
            </p>

            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/signup" className="btn-primary btn-lg">Start my record</Link>
              <Link to="/try" className="btn-secondary btn-lg">
                Try it without an account
              </Link>
            </div>

            <p className="mt-6 max-w-md text-[12.5px] leading-relaxed text-ink-faint">
              Iiris is a decision-support tool, not an eye test. It does not diagnose and
              it does not replace your optometrist.
            </p>
          </div>

          {/* Illustrative trajectory — not real patient data, and labelled as such. */}
          <div className="animate-fade-up [animation-delay:.12s]">
            <HeroCard />
          </div>
        </div>
      </section>

      {/* ------------------------------------------------ how */}
      <section className="relative border-y border-line bg-sand-50">
        <div className="mx-auto max-w-6xl px-5 py-16">
          <div data-reveal>
          <p className="eyebrow">How it works</p>
          <h2 className="mt-2 max-w-lg text-3xl font-semibold">
            Three things, and none of them take long.
          </h2>
          </div>
          <div className="mt-10 grid gap-6 md:grid-cols-3">
            {STEPS.map((s, i) => (
              <div key={s.n} className="card card-hover p-6" data-reveal
                   data-delay={i + 1}>
                <span className="script text-3xl text-sand-600">{s.n}</span>
                <h3 className="mt-2 text-lg font-semibold">{s.title}</h3>
                <p className="lede mt-2 text-[14px]">{s.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ------------------------------------------------ features */}
      <section className="mx-auto max-w-6xl px-5 py-16">
        <div className="grid gap-10 lg:grid-cols-[.8fr_1.2fr]">
          <div data-reveal>
            <p className="eyebrow">What you get</p>
            <h2 className="mt-2 text-3xl font-semibold">
              Built to be honest with you.
            </h2>
            <p className="lede mt-4 text-[15px]">
              Most health tools give you one confident number. Eyes do not work like
              that. Iiris shows you the range it is actually confident about, and tells
              you when a difference is too small to mean anything.
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {FEATURES.map(({ title, body, icon: Icon }, i) => (
              <div key={title} className="card card-hover p-5" data-reveal
                   data-delay={(i % 3) + 1}>
                <div className="text-ink-muted"><Icon /></div>
                <h3 className="mt-3 text-[15px] font-semibold">{title}</h3>
                <p className="lede mt-1.5 text-[13.5px]">{body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ------------------------------------------------ cta */}
      <section className="mx-auto max-w-6xl px-5 pb-20">
        <div data-reveal
             className="grain relative overflow-hidden rounded-xl2 bg-ink px-8 py-14
                        text-center text-sand-100">
          <p className="script relative z-10 text-2xl text-sand-400">start today</p>
          <h2 className="relative z-10 mt-2 text-3xl font-semibold text-sand-50 sm:text-4xl">
            Keep your eye history in one place.
          </h2>
          <p className="relative z-10 mx-auto mt-4 max-w-md text-[15px] text-sand-300">
            Free to set up. Add your first result in under a minute.
          </p>
          <div className="relative z-10 mt-8 flex flex-wrap justify-center gap-3">
            <Link to="/signup"
                  className="btn btn-lg bg-sand-100 text-ink hover:bg-white">
              Create my account
            </Link>
            <Link to="/try"
                  className="btn btn-lg border border-sand-600 text-sand-200
                             hover:bg-ink-soft">
              Just show me the simulator
            </Link>
          </div>
        </div>
      </section>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-5 py-8 text-[12.5px]
                        text-ink-faint sm:flex-row sm:items-center sm:justify-between">
          <Logo size="sm" className="text-ink-muted" />
          <p className="max-w-2xl leading-relaxed">
            Iiris provides model estimates for decision support. It does not diagnose,
            prescribe, or establish that a habit causes a change in your eyes. Always
            speak to a qualified eye-care professional.
          </p>
        </div>
      </footer>
    </div>
  )
}

/* ------------------------------------------------------------ hero visual */

function HeroCard() {
  // A fixed, illustrative curve. Deliberately not live data on a public page.
  const pts = [[0, 18], [1, 34], [2, 47], [3, 66], [4, 82], [5, 96]]
  const w = 300, h = 130
  const x = (i) => 20 + (i / 5) * (w - 40)
  const y = (v) => 18 + (v / 110) * (h - 36)
  const line = pts.map(([i, v], k) => `${k ? 'L' : 'M'}${x(i)},${y(v)}`).join(' ')
  const band = `M${x(3)},${y(66)} L${x(4)},${y(70)} L${x(5)},${y(80)} L${x(5)},${y(112)} L${x(4)},${y(94)} L${x(3)},${y(66)} Z`

  return (
    <div className="card p-6 shadow-lift">
      <div className="flex items-baseline justify-between">
        <div>
          <p className="eyebrow">Prescription over time</p>
          <p className="mt-1 text-2xl font-semibold">−3.15 <span
            className="text-sm font-normal text-ink-muted">D today</span></p>
        </div>
        <span className="chip-watch">moving</span>
      </div>

      <svg viewBox={`0 0 ${w} ${h}`} className="mt-4 w-full" role="img"
           aria-label="Illustrative chart showing a prescription becoming stronger over time, with a widening range of uncertainty">
        {[0, 1, 2, 3].map((g) => (
          <line key={g} x1="20" x2={w - 20} y1={22 + g * 30} y2={22 + g * 30}
                stroke="#E6DFD3" strokeWidth="1" />
        ))}
        <path d={band} fill="rgba(166,149,122,.22)" />
        <path d={line} fill="none" stroke="#1A1815" strokeWidth="2.4"
              strokeLinecap="round" strokeLinejoin="round"
              pathLength="1" strokeDasharray="1"
              style={{ animation: 'draw 1.6s cubic-bezier(.4,0,.2,1) .3s both' }} />
        {pts.slice(0, 4).map(([i, v]) => (
          <circle key={i} cx={x(i)} cy={y(v)} r="3.4" fill="#fff" stroke="#1A1815"
                  strokeWidth="2" />
        ))}
        {pts.slice(4).map(([i, v]) => (
          <circle key={i} cx={x(i)} cy={y(v)} r="3.4" fill="#fff" stroke="#A6957A"
                  strokeWidth="2" />
        ))}
      </svg>

      <div className="mt-3 flex items-center justify-between text-[11px] text-ink-faint">
        <span>2022</span><span>measured</span><span>projected</span><span>2027</span>
      </div>

      <p className="mt-4 rounded-xl bg-sand-200/70 px-3 py-2 text-[11.5px]
                    leading-relaxed text-ink-muted">
        The shaded area is the range Iiris is confident about. It widens further out —
        because honestly, so does the uncertainty.
      </p>
      <p className="mt-2 text-center text-[10.5px] text-ink-faint">
        Illustration, not a real person's data.
      </p>
    </div>
  )
}

/* ------------------------------------------------------------------ icons */
const s = { width: 22, height: 22, viewBox: '0 0 24 24', fill: 'none',
            stroke: 'currentColor', strokeWidth: 1.5, strokeLinecap: 'round',
            strokeLinejoin: 'round', 'aria-hidden': true }
function IconStack() {
  return <svg {...s}><path d="M12 3 3 7.5l9 4.5 9-4.5z"/><path d="m3 12.5 9 4.5 9-4.5"/><path d="m3 17 9 4.5 9-4.5"/></svg>
}
function IconRange() {
  return <svg {...s}><path d="M3 17c4-9 14-9 18-4"/><path d="M3 20c4-11 14-12 18-6"/><path d="M3 14c4-7 14-6 18-2"/></svg>
}
function IconWhy() {
  return <svg {...s}><circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.2 2.4c-.5.2-.7.6-.7 1.1v.5"/><path d="M12 16.5h.01"/></svg>
}
function IconBell() {
  return <svg {...s}><path d="M18 8a6 6 0 1 0-12 0c0 6-2 7-2 7h16s-2-1-2-7"/><path d="M10.5 20a2 2 0 0 0 3 0"/></svg>
}

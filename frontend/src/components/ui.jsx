import React, { useEffect, useRef, useState } from 'react'
import { RULES, checkField } from '../lib/validate'

/* ---------------------------------------------------------------- surfaces */

export function Card({ title, subtitle, actions, children, className = '', bodyClass = '' }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-head">
          <div className="min-w-0">
            {title && <h2 className="text-[17px] font-semibold">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-[13px] text-ink-muted">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      <div className={`card-body ${bodyClass}`}>{children}</div>
    </section>
  )
}

/* ------------------------------------------------------------------- stats */

/** Counts up to the value so a dashboard feels alive without being distracting. */
export function AnimatedNumber({ value, digits = 2, signed = false, duration = 650 }) {
  const [shown, setShown] = useState(value ?? 0)
  const fromRef = useRef(value ?? 0)

  useEffect(() => {
    if (value === null || value === undefined || Number.isNaN(value)) return
    const from = fromRef.current
    const to = value
    if (Math.abs(to - from) < 1e-9) { setShown(to); return }
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      setShown(to); fromRef.current = to; return
    }
    let raf
    const start = performance.now()
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 3)
      setShown(from + (to - from) * eased)
      if (t < 1) raf = requestAnimationFrame(tick)
      else fromRef.current = to
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value, duration])

  if (value === null || value === undefined || Number.isNaN(value)) return <>—</>
  const text = shown.toFixed(digits)
  return <>{signed && shown > 0 ? `+${text}` : text}</>
}

export function Stat({ label, value, unit, sub, tone = 'default', hint }) {
  const tones = {
    default: 'text-ink', calm: 'text-status-calm',
    watch: 'text-status-watch', alert: 'text-status-alert',
  }
  return (
    <div className="card-quiet group px-4 py-3.5 transition-colors hover:border-line-strong">
      <div className="flex items-center gap-1.5">
        <span className="eyebrow">{label}</span>
        {hint && <Tip text={hint} />}
      </div>
      <div className={`stat mt-1.5 text-[26px] font-semibold leading-none ${tones[tone]}`}>
        {value}
        {unit && <span className="ml-1 text-sm font-normal text-ink-muted">{unit}</span>}
      </div>
      {sub && <div className="mt-1.5 text-xs leading-snug text-ink-muted">{sub}</div>}
    </div>
  )
}

/** Small "?" that reveals an explanation — used wherever a clinical term appears. */
export function Tip({ text }) {
  const [open, setOpen] = useState(false)
  return (
    <span className="relative inline-flex">
      <button
        type="button"
        aria-label={`What is this? ${text}`}
        onClick={() => setOpen((o) => !o)}
        onBlur={() => setOpen(false)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        className="flex h-4 w-4 items-center justify-center rounded-full border
                   border-line-strong text-[9px] font-bold text-ink-faint
                   transition-colors hover:border-ink hover:text-ink"
      >?</button>
      {open && (
        <span role="tooltip"
              className="absolute bottom-full left-1/2 z-30 mb-2 w-56 -translate-x-1/2
                         rounded-xl bg-ink px-3 py-2 text-[12px] font-normal
                         leading-relaxed text-sand-100 shadow-lift animate-fade-in">
          {text}
        </span>
      )}
    </span>
  )
}

export function StatusChip({ label, tone = 'neutral', className = '' }) {
  const map = { neutral: 'chip-neutral', calm: 'chip-calm', watch: 'chip-watch',
                alert: 'chip-alert', outline: 'chip-outline' }
  return <span className={`${map[tone] || map.neutral} ${className}`}>{label}</span>
}

/** Maps the API's risk band / myopia category onto a visual tone. */
export function toneForBand(band) {
  return { low: 'calm', moderate: 'watch', high: 'alert' }[band] || 'neutral'
}
export function toneForCategory(label) {
  return { 'No myopia': 'calm', 'Low myopia': 'calm', 'Moderate myopia': 'watch',
           'High myopia': 'alert' }[label] || 'neutral'
}

/* ------------------------------------------------------------------- state */

export function Spinner({ label = 'Loading' }) {
  return (
    <div className="flex items-center justify-center gap-3 py-12 text-sm text-ink-muted">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-sand-400
                       border-t-ink" />
      {label}…
    </div>
  )
}

export function SkeletonCard({ lines = 3 }) {
  return (
    <div className="card p-5">
      <div className="skeleton h-4 w-1/3" />
      <div className="mt-4 space-y-2.5">
        {Array.from({ length: lines }).map((_, i) => (
          <div key={i} className="skeleton h-3" style={{ width: `${90 - i * 12}%` }} />
        ))}
      </div>
    </div>
  )
}

export function ErrorNote({ error, onRetry, className = '' }) {
  if (!error) return null
  return (
    <div className={`note-alert flex flex-wrap items-center justify-between gap-3 ${className}`}
         role="alert">
      <span>{error.message}</span>
      {onRetry && <button className="btn btn-sm btn-secondary" onClick={onRetry}>
        Try again</button>}
    </div>
  )
}

export function EmptyState({ icon, title, children, action }) {
  return (
    <div className="flex flex-col items-center px-6 py-14 text-center">
      {icon && <div className="mb-4 text-ink-faint">{icon}</div>}
      <h3 className="text-lg font-semibold">{title}</h3>
      <p className="lede mt-1.5 max-w-sm text-sm">{children}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

/* ------------------------------------------------------------------- forms */

export function Field({ label, hint, error, children, required }) {
  return (
    <label className="block">
      <span className="label">
        {label}
        {required && <span className="ml-0.5 text-status-alert">*</span>}
      </span>
      {children}
      {error
        ? <span className="mt-1.5 block text-xs text-status-alert">{error}</span>
        : hint && <span className="hint">{hint}</span>}
    </label>
  )
}

/**
 * Number input that reports "" as null, so a blank box means "not measured".
 *
 * Pass `name` and it validates itself against the shared rules, showing the
 * message under the field rather than letting the server reject it later.
 */
export function NumberField({ label, hint, unit, value, onChange, error, name,
                              required, min, max, onValidate, ...rest }) {
  const [touched, setTouched] = useState(false)
  const [settled, setSettled] = useState(false)
  const rule = name ? RULES[name] : null
  const lo = min ?? rule?.min
  const hi = max ?? rule?.max

  // Validate on blur, and also once typing pauses -- otherwise someone who
  // enters an impossible value and just sits there gets no feedback at all.
  // The delay stops "must be at least 15" flashing while they type "2" of "23".
  useEffect(() => {
    setSettled(false)
    if (value === null || value === undefined || value === '') return
    const t = setTimeout(() => setSettled(true), 700)
    return () => clearTimeout(t)
  }, [value])

  const localError = name && (touched || settled)
    ? checkField(name, value, { required }) : null
  const shown = error || localError

  useEffect(() => {
    if (name && onValidate) onValidate(name, checkField(name, value, { required }))
  }, [value]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Field label={label} hint={hint} error={shown} required={required}>
      <div className="relative">
        <input
          type="number" inputMode="decimal"
          min={lo} max={hi}
          aria-invalid={!!shown}
          className={`input ${unit ? 'pr-16' : ''} ${shown ? 'input-error' : ''}`}
          value={value ?? ''}
          onBlur={() => setTouched(true)}
          onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
          {...rest}
        />
        {unit && (
          <span className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2
                           text-xs text-ink-faint">{unit}</span>
        )}
      </div>
    </Field>
  )
}

/** Slider + live value. Used everywhere an exposure is adjusted. */
export function SliderField({ label, unit, value, min, max, step, onChange,
                              baseline, hint, changed, onReset }) {
  return (
    <div className={`rounded-xl border p-3.5 transition-all duration-200 ${
      changed ? 'border-ink bg-sand-200/60' : 'border-line bg-white hover:border-line-strong'}`}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[13px] font-medium text-ink-soft">{label}</span>
        {baseline !== undefined && baseline !== null && (
          <span className="text-[11px] text-ink-faint">now {Number(baseline).toFixed(
            step < 1 ? 2 : 0)} {unit}</span>
        )}
      </div>
      <input type="range" className="mt-3" min={min} max={max} step={step}
             value={value} aria-label={label}
             onChange={(e) => onChange(Number(e.target.value))} />
      <div className="mt-2 flex items-center justify-between">
        <span className="stat text-[15px] font-semibold">
          {Number(value).toFixed(step < 1 ? 2 : 0)}
          <span className="ml-1 text-[11px] font-normal text-ink-muted">{unit}</span>
        </span>
        {changed && onReset && (
          <button type="button" onClick={onReset}
                  className="text-[11px] font-medium text-ink-muted underline
                             underline-offset-2 hover:text-ink">reset</button>
        )}
      </div>
      {hint && <p className="mt-2 text-[11px] leading-relaxed text-ink-faint">{hint}</p>}
    </div>
  )
}

/* ------------------------------------------------------------- disclosures */

/** The clinical-safety line. Present wherever a model number is shown. */
export function Disclaimer({ text, tone = 'quiet', className = '' }) {
  if (!text) return null
  return (
    <p className={`mt-4 text-[12px] leading-relaxed ${
      tone === 'watch' ? 'text-status-watch' : 'text-ink-faint'} ${className}`}>
      {text}
    </p>
  )
}

export function Collapsible({ label, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border-t border-line pt-3">
      <button onClick={() => setOpen((o) => !o)}
              className="flex w-full items-center justify-between gap-2 text-left
                         text-[13px] font-medium text-ink-muted hover:text-ink">
        {label}
        <svg width="12" height="8" viewBox="0 0 12 8" aria-hidden="true"
             className={`transition-transform duration-200 ${open ? 'rotate-180' : ''}`}>
          <path d="M1 1.5 6 6.5 11 1.5" stroke="currentColor" strokeWidth="1.6"
                fill="none" strokeLinecap="round" />
        </svg>
      </button>
      {open && <div className="mt-3 animate-fade-in">{children}</div>}
    </div>
  )
}

/* ------------------------------------------------------------------ toasts */

const ToastCtx = React.createContext(null)

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const push = React.useCallback((message, tone = 'calm') => {
    const id = Math.random().toString(36).slice(2)
    setToasts((t) => [...t, { id, message, tone }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-6 z-50 flex
                      flex-col items-center gap-2 px-4" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id}
               className={`pointer-events-auto animate-fade-up rounded-full px-5 py-2.5
                           text-sm font-medium shadow-lift ${
                 t.tone === 'alert' ? 'bg-status-alert text-white'
                   : t.tone === 'watch' ? 'bg-status-watch text-white'
                   : 'bg-ink text-sand-50'}`}>
            {t.message}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

export function useToast() {
  const ctx = React.useContext(ToastCtx)
  return ctx || (() => {})
}

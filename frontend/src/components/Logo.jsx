/**
 * The Iiris eye.
 *
 * It blinks on its own every few seconds, occasionally winks instead, and
 * sometimes glances left and right. Clicking it always makes it wink back.
 *
 * Timing is randomised so it never looks metronomic — a fixed-interval blink
 * reads as a loading spinner, not as a creature. All of it is disabled under
 * prefers-reduced-motion.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react'

const SIZES = {
  xs: { px: 18, text: 'text-lg' },
  sm: { px: 24, text: 'text-xl' },
  md: { px: 30, text: 'text-2xl' },
  lg: { px: 44, text: 'text-4xl' },
  xl: { px: 68, text: 'text-6xl' },
}

// How long each expression lasts, matched to the keyframes in index.css.
const DURATION = { blink: 260, wink: 520, look: 900 }

function prefersReducedMotion() {
  return typeof window !== 'undefined'
    && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

export default function Logo({ size = 'md', className = '', showWordmark = true,
                               idle = true }) {
  const { px, text } = SIZES[size] || SIZES.md
  const [expression, setExpression] = useState('open')
  const timers = useRef([])

  const clearTimers = () => { timers.current.forEach(clearTimeout); timers.current = [] }

  const play = useCallback((next) => {
    if (prefersReducedMotion()) return
    setExpression(next)
    timers.current.push(setTimeout(() => setExpression('open'), DURATION[next]))
  }, [])

  // Idle loop: mostly blinks, sometimes a wink, sometimes a glance.
  useEffect(() => {
    if (!idle || prefersReducedMotion()) return
    let cancelled = false
    const schedule = () => {
      const wait = 2800 + Math.random() * 4200
      const t = setTimeout(() => {
        if (cancelled) return
        const roll = Math.random()
        const next = roll < 0.18 ? 'wink' : roll < 0.32 ? 'look' : 'blink'
        play(next)
        // A double blink now and then, the way real eyes do it.
        if (next === 'blink' && Math.random() < 0.22) {
          timers.current.push(setTimeout(() => play('blink'), 320))
        }
        schedule()
      }, wait)
      timers.current.push(t)
    }
    schedule()
    return () => { cancelled = true; clearTimers() }
  }, [idle, play])

  useEffect(() => clearTimers, [])

  const eyeClass = expression === 'blink' ? 'animate-iiris-blink'
    : expression === 'wink' ? 'animate-iiris-wink' : ''
  const irisClass = expression === 'look' ? 'animate-iiris-look' : ''

  return (
    <span
      className={`group inline-flex select-none items-center gap-2 ${className}`}
      onMouseEnter={() => expression === 'open' && play('look')}
      onClick={() => play('wink')}
    >
      <svg width={px} height={px} viewBox="0 0 40 40" aria-hidden="true"
           className="shrink-0 overflow-visible">
        <g className={`origin-center ${eyeClass}`}
           style={{ transformBox: 'fill-box', transformOrigin: 'center' }}>
          {/* eye outline */}
          <path d="M2.5 20C2.5 20 9 9.5 20 9.5S37.5 20 37.5 20 31 30.5 20 30.5 2.5 20 2.5 20Z"
                fill="none" stroke="currentColor" strokeWidth="2.1"
                strokeLinejoin="round" />
          {/* iris + pupil + catchlight */}
          <g className={irisClass}>
            <circle cx="20" cy="20" r="6.4" fill="currentColor" />
            <circle cx="22.3" cy="17.6" r="2.1" className="fill-sand-100" />
            <circle cx="17.6" cy="22.4" r="0.9" className="fill-sand-100 opacity-60" />
          </g>
        </g>
        {/* lash flick, only while winking */}
        {expression === 'wink' && (
          <path d="M31 14.5c1.6-1 3-1.6 4.4-1.9" stroke="currentColor" strokeWidth="1.7"
                strokeLinecap="round" fill="none" className="animate-fade-in" />
        )}
      </svg>
      {showWordmark && (
        <span className={`font-hand font-bold leading-none ${text}`}>Iiris</span>
      )}
    </span>
  )
}

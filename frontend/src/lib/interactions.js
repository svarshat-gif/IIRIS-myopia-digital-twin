/**
 * Global click ripple.
 *
 * Attached once at the app root rather than wired into every button, so every
 * .btn on every page gets it without changing a single component. Skipped
 * entirely under prefers-reduced-motion.
 */
export function installRipple() {
  if (typeof document === 'undefined') return () => {}
  if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return () => {}

  const onPointerDown = (e) => {
    const btn = e.target.closest?.('.btn, .nav-link')
    if (!btn || btn.disabled) return

    const rect = btn.getBoundingClientRect()
    const size = Math.max(rect.width, rect.height)
    const span = document.createElement('span')
    span.className = 'ripple'
    span.style.width = span.style.height = `${size}px`
    span.style.left = `${e.clientX - rect.left - size / 2}px`
    span.style.top = `${e.clientY - rect.top - size / 2}px`
    // The button may not be positioned; the ripple needs a containing block.
    if (getComputedStyle(btn).position === 'static') btn.style.position = 'relative'
    btn.appendChild(span)
    span.addEventListener('animationend', () => span.remove(), { once: true })
  }

  document.addEventListener('pointerdown', onPointerDown)
  return () => document.removeEventListener('pointerdown', onPointerDown)
}


/**
 * Reveal-on-scroll for landing sections.
 *
 * Uses IntersectionObserver so nothing animates until it is actually near the
 * viewport, and each element only animates once. Under prefers-reduced-motion
 * everything is simply shown.
 */
export function installScrollReveal(root = document) {
  const els = Array.from(root.querySelectorAll('[data-reveal]'))
  if (!els.length) return () => {}

  if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
    els.forEach((el) => el.classList.add('revealed'))
    return () => {}
  }

  const io = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return
      entry.target.classList.add('revealed')
      io.unobserve(entry.target)
    })
  }, { rootMargin: '0px 0px -12% 0px', threshold: 0.08 })

  els.forEach((el) => io.observe(el))
  return () => io.disconnect()
}

import Logo from '../components/Logo'
/** The simulator, available without an account. The product's front door. */
import React from 'react'
import { Link } from 'react-router-dom'

import Simulator from './Simulator'

export default function PublicSimulator() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-sand-50">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-5 py-4">
          <Link to="/" className="text-ink"><Logo size="sm" /></Link>
          <nav className="flex items-center gap-2">
            <Link to="/login" className="btn btn-ghost btn-sm">Sign in</Link>
            <Link to="/signup" className="btn-primary btn-sm">Create account</Link>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-5 py-8">
        <Simulator publicMode />
      </main>
      <footer className="border-t border-line">
        <p className="mx-auto max-w-5xl px-5 py-6 text-[12px] leading-relaxed
                      text-ink-faint">
          Nothing you type here is saved. Iiris is a decision-support tool, not an eye
          test — it does not diagnose, and it is not a substitute for seeing an
          optometrist.
        </p>
      </footer>
    </div>
  )
}

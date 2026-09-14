import React, { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, fmt } from '../lib/api'
import {
  Card, EmptyState, ErrorNote, Field, SkeletonCard, StatusChip, useToast,
} from '../components/ui'

const today = () => new Date().toISOString().slice(0, 10)
const BLANK = {
  scheduled_for: today(), time_label: '', clinic: '', practitioner: '',
  reason: '', status: 'scheduled', notes: '',
}

const STATUS_TONE = { scheduled: 'outline', completed: 'calm', cancelled: 'neutral' }

export default function Appointments() {
  const [params, setParams] = useSearchParams()
  const [items, setItems] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(params.get('add') === '1' ? BLANK : null)
  const toast = useToast()

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try { setItems(await api.appointments()) }
    catch (e) { setError(e) } finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])

  function close() {
    setEditing(null)
    if (params.get('add')) { params.delete('add'); setParams(params, { replace: true }) }
  }

  async function save(form) {
    const body = { ...form }
    for (const k of ['time_label', 'clinic', 'practitioner', 'reason', 'notes'])
      if (!body[k]) body[k] = null
    if (form.appointment_id) {
      const { appointment_id, ...rest } = body
      await api.updateAppointment(appointment_id, rest)
      toast('Appointment updated')
    } else {
      await api.addAppointment(body)
      toast('Appointment saved')
    }
    close(); load()
  }

  async function remove(a) {
    if (!window.confirm(`Delete the appointment on ${fmt.date(a.scheduled_for)}?`)) return
    await api.deleteAppointment(a.appointment_id)
    toast('Appointment deleted')
    load()
  }

  const upcoming = (items || []).filter((a) => !a.is_past && a.status === 'scheduled')
    .sort((a, b) => a.scheduled_for.localeCompare(b.scheduled_for))
  const past = (items || []).filter((a) => a.is_past || a.status !== 'scheduled')

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="script text-2xl text-ink-muted">visits, past and planned</p>
          <h1 className="text-3xl font-semibold">Appointments</h1>
        </div>
        {!editing && (
          <button className="btn-primary" onClick={() => setEditing(BLANK)}>
            + Add appointment
          </button>
        )}
      </div>

      {editing && <AppointmentForm initial={editing} onSave={save} onCancel={close} />}

      <ErrorNote error={error} onRetry={load} />

      {loading ? <SkeletonCard lines={4} /> : (
        <>
          <section>
            <h2 className="mb-3 text-[15px] font-semibold">
              Coming up {upcoming.length > 0 && (
                <span className="ml-1 text-ink-faint">({upcoming.length})</span>)}
            </h2>
            {upcoming.length === 0 ? (
              <Card>
                <EmptyState title="Nothing booked"
                            action={<button className="btn-secondary"
                                            onClick={() => setEditing(BLANK)}>
                              Add an appointment</button>}>
                  Children being monitored for short-sightedness are often seen every
                  six months. Ask your optometrist what interval suits you.
                </EmptyState>
              </Card>
            ) : (
              <div className="space-y-3 stagger">
                {upcoming.map((a) => (
                  <AppointmentRow key={a.appointment_id} a={a} highlight
                                  onEdit={() => setEditing(a)}
                                  onDelete={() => remove(a)} />
                ))}
              </div>
            )}
          </section>

          {past.length > 0 && (
            <section>
              <h2 className="mb-3 mt-8 text-[15px] font-semibold">
                Previous visits <span className="ml-1 text-ink-faint">({past.length})</span>
              </h2>
              <div className="space-y-2.5">
                {past.map((a) => (
                  <AppointmentRow key={a.appointment_id} a={a}
                                  onEdit={() => setEditing(a)}
                                  onDelete={() => remove(a)} />
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  )
}

function AppointmentRow({ a, highlight, onEdit, onDelete }) {
  const days = Math.round(
    (new Date(a.scheduled_for + 'T00:00:00') - new Date().setHours(0, 0, 0, 0))
    / 86400000)
  return (
    <div className={`card flex flex-wrap items-center gap-4 p-4 transition-shadow
                     hover:shadow-lift ${highlight ? 'ring-1 ring-ink/10' : ''}`}>
      {/* date block */}
      <div className={`flex h-14 w-14 shrink-0 flex-col items-center justify-center
                       rounded-xl ${highlight ? 'bg-ink text-sand-50'
                                              : 'bg-sand-200 text-ink-muted'}`}>
        <span className="text-[10px] font-medium uppercase tracking-wider">
          {new Date(a.scheduled_for + 'T00:00:00')
            .toLocaleDateString(undefined, { month: 'short' })}
        </span>
        <span className="stat text-lg font-semibold leading-none">
          {new Date(a.scheduled_for + 'T00:00:00').getDate()}
        </span>
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-medium">{a.reason || 'Eye appointment'}</p>
          <StatusChip label={a.status} tone={STATUS_TONE[a.status] || 'neutral'} />
          {highlight && (
            <span className="text-[12px] text-ink-muted">{fmt.relative(days)}</span>
          )}
        </div>
        <p className="mt-0.5 text-[13px] text-ink-muted">
          {[fmt.date(a.scheduled_for), a.time_label, a.clinic, a.practitioner]
            .filter(Boolean).join(' · ')}
        </p>
        {a.notes && <p className="mt-1.5 text-[12.5px] text-ink-faint">{a.notes}</p>}
      </div>

      <div className="flex gap-1">
        <button className="btn btn-ghost btn-sm" onClick={onEdit}>Edit</button>
        <button onClick={onDelete}
                className="btn btn-ghost btn-sm text-ink-faint hover:text-status-alert">
          Delete
        </button>
      </div>
    </div>
  )
}

function AppointmentForm({ initial, onSave, onCancel }) {
  const [form, setForm] = useState({ ...BLANK, ...initial })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setError(null)
    try { await onSave(form) } catch (err) { setError(err) } finally { setBusy(false) }
  }

  return (
    <Card title={form.appointment_id ? 'Edit appointment' : 'Add an appointment'}>
      <form onSubmit={submit} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Date" required>
            <input className="input" type="date" required value={form.scheduled_for}
                   onChange={set('scheduled_for')} />
          </Field>
          <Field label="Time" hint="Free text — whatever your letter says.">
            <input className="input" value={form.time_label || ''}
                   placeholder="10:30 AM" onChange={set('time_label')} />
          </Field>
          <Field label="Status">
            <select className="input" value={form.status} onChange={set('status')}>
              <option value="scheduled">Scheduled</option>
              <option value="completed">Completed</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </Field>
          <Field label="Clinic">
            <input className="input" value={form.clinic || ''}
                   placeholder="City Eye Centre" onChange={set('clinic')} />
          </Field>
          <Field label="Who you are seeing">
            <input className="input" value={form.practitioner || ''}
                   placeholder="Dr Menon" onChange={set('practitioner')} />
          </Field>
          <Field label="Reason">
            <input className="input" value={form.reason || ''}
                   placeholder="6-month review" onChange={set('reason')} />
          </Field>
        </div>
        <Field label="Notes" hint="Questions to ask, or what came out of the visit.">
          <textarea className="input min-h-[80px] resize-y" value={form.notes || ''}
                    onChange={set('notes')} />
        </Field>

        <ErrorNote error={error} />

        <div className="flex gap-3">
          <button className="btn-primary" disabled={busy}>
            {busy ? 'Saving…' : 'Save appointment'}
          </button>
          <button type="button" className="btn btn-ghost" onClick={onCancel}>Cancel</button>
        </div>
      </form>
    </Card>
  )
}

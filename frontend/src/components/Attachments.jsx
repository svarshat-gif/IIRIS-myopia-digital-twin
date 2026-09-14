/**
 * Prescription photos and scan reports.
 *
 * Files are protected by the session token, so an <img src="/api/..."> cannot
 * load them — the bytes are fetched with the header and wrapped in an object
 * URL, which is revoked when the thumbnail unmounts.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react'
import { api, fmt } from '../lib/api'
import { Card, EmptyState, ErrorNote, Field, useToast } from './ui'

const KINDS = [
  ['prescription', 'Prescription'],
  ['scan', 'Scan / biometry'],
  ['report', 'Clinic report'],
  ['other', 'Other'],
]
const ACCEPT = 'image/jpeg,image/png,image/gif,image/webp,image/heic,application/pdf'

/** Loads a protected image and cleans its object URL up after itself. */
function Thumb({ attachment, onOpen }) {
  const [url, setUrl] = useState(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!attachment.is_image) return
    let revoked = false
    let made = null
    api.attachmentBlobUrl(attachment.attachment_id)
      .then((u) => { if (revoked) { URL.revokeObjectURL(u); return } made = u; setUrl(u) })
      .catch(() => setFailed(true))
    return () => { revoked = true; if (made) URL.revokeObjectURL(made) }
  }, [attachment.attachment_id, attachment.is_image])

  if (!attachment.is_image) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-sand-200">
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" strokeWidth="1.4" className="text-ink-muted"
             aria-hidden="true">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <path d="M14 2v6h6" />
        </svg>
      </div>
    )
  }
  if (failed) {
    return <div className="flex h-full w-full items-center justify-center bg-sand-200
                           text-[10px] text-ink-faint">unavailable</div>
  }
  if (!url) return <div className="h-full w-full animate-pulse bg-sand-300" />
  return (
    <button onClick={() => onOpen(url)} className="h-full w-full">
      <img src={url} alt={attachment.note || attachment.filename}
           className="h-full w-full object-cover transition-transform duration-500
                      hover:scale-105" />
    </button>
  )
}

export default function Attachments({ observationId = null, compact = false }) {
  const [items, setItems] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState(0)
  const [dragging, setDragging] = useState(false)
  const [kind, setKind] = useState('prescription')
  const [note, setNote] = useState('')
  const [lightbox, setLightbox] = useState(null)
  const inputRef = useRef(null)
  const toast = useToast()

  const load = useCallback(async () => {
    try { setItems((await api.attachments()).attachments) }
    catch (e) { setError(e) }
  }, [])
  useEffect(() => { load() }, [load])

  const send = useCallback(async (files) => {
    const list = Array.from(files || [])
    if (!list.length) return
    setBusy(true); setError(null)
    let saved = 0
    for (const file of list) {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('kind', kind)
      if (note) fd.append('note', note)
      if (observationId) fd.append('observation_id', observationId)
      try {
        await api.uploadAttachment(fd, setProgress)
        saved += 1
      } catch (e) { setError(e); break }
    }
    setBusy(false); setProgress(0); setNote('')
    if (saved) {
      toast(saved === 1 ? 'File saved' : `${saved} files saved`)
      load()
    }
  }, [kind, note, observationId, load, toast])

  async function remove(a) {
    if (!window.confirm(`Delete "${a.filename}"? This cannot be undone.`)) return
    try { await api.deleteAttachment(a.attachment_id); toast('File deleted'); load() }
    catch (e) { setError(e) }
  }

  const shown = observationId
    ? (items || []).filter((a) => a.observation_id === observationId)
    : (items || [])

  const dropzone = (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => { e.preventDefault(); setDragging(false); send(e.dataTransfer.files) }}
      onClick={() => inputRef.current?.click()}
      role="button" tabIndex={0}
      onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && inputRef.current?.click()}
      className={`cursor-pointer rounded-xl2 border-2 border-dashed p-6 text-center
                  transition-all duration-200 ${
        dragging ? 'border-ink bg-sand-200 scale-[1.01]'
                 : 'border-line-strong bg-sand-50 hover:border-ink-faint hover:bg-sand-100'}`}
    >
      <input ref={inputRef} type="file" accept={ACCEPT} multiple className="hidden"
             onChange={(e) => { send(e.target.files); e.target.value = '' }} />
      <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"
           className={`mx-auto text-ink-muted transition-transform duration-200 ${
             dragging ? 'scale-110 -translate-y-0.5' : ''}`} aria-hidden="true">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <path d="M17 8l-5-5-5 5" /><path d="M12 3v13" />
      </svg>
      <p className="mt-2.5 text-[14px] font-medium">
        {dragging ? 'Drop it here' : 'Add a photo of your prescription'}
      </p>
      <p className="mt-1 text-[12px] text-ink-muted">
        Drag one in, or click to choose. JPEG, PNG, HEIC or PDF, up to 10 MB.
      </p>
      {busy && (
        <div className="mx-auto mt-3 h-1.5 w-40 overflow-hidden rounded-full bg-sand-300">
          <div className="h-full rounded-full bg-ink transition-all duration-200"
               style={{ width: `${progress || 8}%` }} />
        </div>
      )}
    </div>
  )

  const grid = shown.length > 0 && (
    <ul className="mt-4 grid gap-3 stagger sm:grid-cols-2 lg:grid-cols-3">
      {shown.map((a) => (
        <li key={a.attachment_id}
            className="pop-in overflow-hidden rounded-xl border border-line bg-white
                       transition-shadow duration-300 hover:shadow-lift">
          <div className="aspect-[4/3] overflow-hidden bg-sand-100">
            <Thumb attachment={a} onOpen={setLightbox} />
          </div>
          <div className="p-3">
            <p className="truncate text-[13px] font-medium">
              {a.note || a.filename}
            </p>
            <p className="mt-0.5 text-[11px] text-ink-faint">
              {KINDS.find(([k]) => k === a.kind)?.[1] || a.kind} · {a.size_label} ·{' '}
              {fmt.date(a.created_at.slice(0, 10))}
            </p>
            <div className="mt-2 flex gap-1">
              <button className="btn btn-ghost btn-sm"
                      onClick={async () => {
                        try { setLightbox(await api.attachmentBlobUrl(a.attachment_id)) }
                        catch (e) { setError(e) }
                      }}>
                View
              </button>
              <button onClick={() => remove(a)}
                      className="btn btn-ghost btn-sm text-ink-faint
                                 hover:text-status-alert">
                Delete
              </button>
            </div>
          </div>
        </li>
      ))}
    </ul>
  )

  const body = (
    <>
      {!compact && (
        <div className="mb-4 grid gap-3 sm:grid-cols-2">
          <Field label="What is this?">
            <select className="input" value={kind} onChange={(e) => setKind(e.target.value)}>
              {KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </Field>
          <Field label="Label (optional)" hint="e.g. “Sept 2026 — City Eye Centre”">
            <input className="input" value={note} placeholder="Add a short label"
                   onChange={(e) => setNote(e.target.value)} />
          </Field>
        </div>
      )}

      {dropzone}
      <ErrorNote error={error} className="mt-3" />

      {items === null ? (
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          {[0, 1, 2].map((i) => <div key={i} className="skeleton h-40" />)}
        </div>
      ) : shown.length === 0 ? (
        <p className="mt-4 text-center text-[13px] text-ink-muted">
          Nothing uploaded yet. Photos you add stay in your account and are only
          visible to you.
        </p>
      ) : grid}

      {lightbox && (
        <div role="dialog" aria-modal="true"
             className="fixed inset-0 z-50 flex animate-fade-in items-center
                        justify-center bg-ink/80 p-6"
             onClick={() => { URL.revokeObjectURL(lightbox); setLightbox(null) }}>
          <img src={lightbox} alt="Uploaded prescription"
               className="pop-in max-h-full max-w-full rounded-xl shadow-lift" />
          <button className="absolute right-6 top-6 rounded-full bg-sand-100 px-4 py-2
                             text-sm font-medium text-ink"
                  onClick={() => { URL.revokeObjectURL(lightbox); setLightbox(null) }}>
            Close
          </button>
        </div>
      )}
    </>
  )

  if (compact) return body

  return (
    <Card title="Prescription photos & reports"
          subtitle="Keep the paperwork with the numbers. Only you can see these.">
      {body}
    </Card>
  )
}

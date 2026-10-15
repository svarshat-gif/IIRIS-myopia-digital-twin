/**
 * Iiris API client.
 *
 * Holds the session token, attaches it to every request, and surfaces errors in
 * language a person can act on rather than an HTTP status.
 */
const BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
const PREFIX = `${BASE}/api/v1`
const TOKEN_KEY = 'iiris.token'

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export const token = {
  get: () => { try { return localStorage.getItem(TOKEN_KEY) } catch { return null } },
  set: (v) => { try { v ? localStorage.setItem(TOKEN_KEY, v)
                        : localStorage.removeItem(TOKEN_KEY) } catch { /* private mode */ } },
}

// Set by AuthContext so an expired session logs the user out everywhere at once.
let onUnauthorized = null
export function setUnauthorizedHandler(fn) { onUnauthorized = fn }

async function request(path, { method = 'GET', body, auth = true, signal } = {}) {
  const headers = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const t = auth ? token.get() : null
  if (t) headers.Authorization = `Bearer ${t}`

  let res
  try {
    res = await fetch(`${PREFIX}${path}`, {
      method, headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })
  } catch (err) {
    if (err.name === 'AbortError') throw err
    throw new ApiError(
      "Can't reach Iiris right now. Check your connection and try again.", 0, null)
  }

  if (res.status === 401 && auth && token.get()) {
    token.set(null)
    onUnauthorized?.()
  }

  const text = await res.text()
  let payload = null
  if (text) { try { payload = JSON.parse(text) } catch { payload = text } }
  if (!res.ok) throw new ApiError(readable(res.status, payload?.detail ?? payload),
                                  res.status, payload?.detail ?? payload)
  return payload
}

function readable(status, detail) {
  if (typeof detail === 'string') return detail
  if (detail?.message) return [detail.message, ...(detail.errors || [])].join(' ')
  if (Array.isArray(detail)) {
    // FastAPI validation errors -> "Age must be at least 3"
    return detail.map((d) => {
      const field = (d.loc || []).filter((p) => p !== 'body').join(' ')
      const msg = d.msg
        .replace(/^Value error, /, '')
        .replace('Input should be greater than or equal to', 'must be at least')
        .replace('Input should be less than or equal to', 'must be at most')
        .replace('Input should be a valid number', 'must be a number')
        .replace('Field required', 'is required')
      return `${field ? prettyField(field) + ' ' : ''}${msg}`
    }).join('. ')
  }
  if (status === 503) return 'The prediction model is not available on the server yet.'
  if (status === 413) return 'That file is too large. The limit is 10 MB.'
  if (status === 404) return "We couldn't find that."
  return `Something went wrong (${status}).`
}

/**
 * The API speaks in schema field names ("axial_length"); the interface speaks in
 * plain words ("Eye length"). Without this map a user sees an error naming a
 * field that does not appear anywhere on their screen.
 */
export const FIELD_LABELS = {
  age: 'Age',
  spherical_equivalent: 'Prescription',
  axial_length: 'Eye length',
  visual_acuity: 'Vision',
  corneal_curvature: 'Corneal curvature',
  parental_myopia: 'Short-sighted parents',
  screen_time_hours: 'Screen time',
  near_work_min: 'Reading & homework',
  outdoor_min: 'Time outdoors',
  sleep_hours: 'Sleep',
  viewing_distance_cm: 'Screen distance',
  posture_score: 'Posture',
  continuous_session_min: 'Time before a break',
  visit_date: 'Date of test',
  scheduled_for: 'Date',
  full_name: 'Name',
  email: 'Email',
  password: 'Password',
  treatment: 'Treatment',
  years: 'Years ahead',
}

function prettyField(f) {
  const key = f.trim().split(' ').pop()
  return FIELD_LABELS[key]
    || key.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())
}

/**
 * Multipart upload with progress. Uses XHR rather than fetch because fetch still
 * cannot report upload progress, and a photo on a phone connection needs a bar.
 */
function upload(path, formData, onProgress, method = 'POST') {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open(method, `${PREFIX}${path}`)
    const t = token.get()
    if (t) xhr.setRequestHeader('Authorization', `Bearer ${t}`)

    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100))
      }
    }
    xhr.onload = () => {
      let payload = null
      try { payload = JSON.parse(xhr.responseText) } catch { payload = xhr.responseText }
      if (xhr.status >= 200 && xhr.status < 300) return resolve(payload)
      if (xhr.status === 401) { token.set(null); onUnauthorized?.() }
      reject(new ApiError(readable(xhr.status, payload?.detail ?? payload),
                          xhr.status, payload?.detail ?? payload))
    }
    xhr.onerror = () => reject(new ApiError(
      "Couldn't upload that file. Check your connection and try again.", 0, null))
    xhr.send(formData)
  })
}

/**
 * Fetch a protected file and hand back an object URL.
 * A plain <img src> cannot carry the Authorization header, so the bytes are
 * fetched first and wrapped. Callers must revoke the URL when done.
 */
async function blobUrl(path) {
  const headers = {}
  const t = token.get()
  if (t) headers.Authorization = `Bearer ${t}`
  const res = await fetch(`${PREFIX}${path}`, { headers })
  if (!res.ok) throw new ApiError('That file could not be loaded.', res.status, null)
  return URL.createObjectURL(await res.blob())
}

export const api = {
  cohort: () => request('/patients?limit=1000'),
  patientTwin: (id) => request(`/patients/${encodeURIComponent(id)}/twin`),
  patientVersions: (id) => request(`/patients/${encodeURIComponent(id)}/twin/versions`),
  patientExplanation: (id) => request(`/patients/${encodeURIComponent(id)}/explanation`),
  patientVisit: (id, body) => request(`/patients/${encodeURIComponent(id)}/observations`, { method: 'POST', body }),
  patientDiff: (id, from, to) => request(`/patients/${encodeURIComponent(id)}/twin/compare?from_version=${from}&to_version=${to}`),
  patientQuery: (id, question) => request(`/patients/${encodeURIComponent(id)}/query`, { method: 'POST', body: { question } }),
  patientScenarios: (id, scenarios) => request(`/patients/${encodeURIComponent(id)}/simulate/batch`, { method: 'POST', body: { scenarios } }),
  // --- public ---
  health: () => request('/health', { auth: false }),
  simulatorInputs: () => request('/simulator/inputs', { auth: false }),
  quickProject: (body) => request('/simulator/project', { method: 'POST', body,
                                                          auth: false }),
  modelCard: () => request('/meta/model', { auth: false }),
  evidence: (q) => request(`/evidence/search?q=${encodeURIComponent(q)}&limit=6`,
                           { auth: false }),

  // --- account ---
  signup: (body) => request('/auth/signup', { method: 'POST', body, auth: false }),
  login: (body) => request('/auth/login', { method: 'POST', body, auth: false }),
  me: () => request('/auth/me'),
  updateProfile: (body) => request('/auth/me', { method: 'PATCH', body }),
  changePassword: (body) => request('/auth/change-password', { method: 'POST', body }),

  // --- my record ---
  summary: () => request('/me/summary'),
  twin: () => request('/me/twin'),
  records: () => request('/me/records'),
  addRecord: (body) => request('/me/records', { method: 'POST', body }),
  deleteRecord: (id) => request(`/me/records/${id}`, { method: 'DELETE' }),
  prediction: () => request('/me/prediction'),
  explanation: (target = 'se_12m') => request(`/me/explanation?target=${target}`),
  versions: () => request('/me/versions'),
  fhir: () => request('/me/fhir'),

  simulate: (body) => request('/me/simulate', { method: 'POST', body }),
  sensitivity: (body) => request('/me/sensitivity', { method: 'POST', body }),
  project: (body) => request('/me/project', { method: 'POST', body }),

  // --- files (prescription photos, scan reports) ---
  attachments: () => request('/me/attachments'),
  uploadAttachment: (formData, onProgress) =>
    upload('/me/attachments', formData, onProgress),
  updateAttachment: (id, formData) => upload(`/me/attachments/${id}`, formData, null,
                                             'PATCH'),
  deleteAttachment: (id) => request(`/me/attachments/${id}`, { method: 'DELETE' }),
  attachmentBlobUrl: (id) => blobUrl(`/me/attachments/${id}/file`),

  appointments: () => request('/me/appointments'),
  addAppointment: (body) => request('/me/appointments', { method: 'POST', body }),
  updateAppointment: (id, body) =>
    request(`/me/appointments/${id}`, { method: 'PATCH', body }),
  deleteAppointment: (id) => request(`/me/appointments/${id}`, { method: 'DELETE' }),

  // --- assistant ---
  ask: (patientId, question) =>
    request(`/patients/${patientId}/query`, { method: 'POST',
                                              body: { question } }),
  modifiableInputs: () => request('/meta/inputs', { auth: false }),
}

/* ---------------------------------------------------------------- formatting */

export const fmt = {
  /** Dioptres always carry an explicit sign: -2.50 D and +0.25 D read differently. */
  dioptre: (v, digits = 2) =>
    v === null || v === undefined || Number.isNaN(v)
      ? '—' : `${v > 0 ? '+' : ''}${Number(v).toFixed(digits)}`,
  mm: (v, digits = 2) =>
    v === null || v === undefined || Number.isNaN(v) ? '—' : Number(v).toFixed(digits),
  num: (v, digits = 1) =>
    v === null || v === undefined || Number.isNaN(v) ? '—' : Number(v).toFixed(digits),
  signed: (v, digits = 2) =>
    v === null || v === undefined ? '—' : `${v > 0 ? '+' : ''}${Number(v).toFixed(digits)}`,
  pct: (v, digits = 0) =>
    v === null || v === undefined ? '—' : `${(Number(v) * 100).toFixed(digits)}%`,
  date: (s) => (s ? new Date(s + (s.length === 10 ? 'T00:00:00' : ''))
    .toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
    : '—'),
  monthYear: (s) => (s ? new Date(s + (s.length === 10 ? 'T00:00:00' : ''))
    .toLocaleDateString(undefined, { month: 'short', year: 'numeric' }) : '—'),
  /** "in 3 months", "2 weeks ago" — friendlier than a bare date on a dashboard. */
  relative: (days) => {
    if (days === null || days === undefined) return ''
    const abs = Math.abs(days)
    const unit = abs < 14 ? [abs, 'day'] : abs < 60 ? [Math.round(abs / 7), 'week']
      : abs < 365 ? [Math.round(abs / 30.4), 'month'] : [(abs / 365).toFixed(1), 'year']
    const label = `${unit[0]} ${unit[1]}${Number(unit[0]) === 1 ? '' : 's'}`
    return days >= 0 ? `in ${label}` : `${label} ago`
  },
}

/** Direction of a change in refraction, in plain words. */
export function seDirection(delta) {
  if (delta === null || delta === undefined || Math.abs(delta) < 0.01) return 'steady'
  return delta < 0 ? 'more short-sighted' : 'less short-sighted'
}

/**
 * Client-side field rules.
 *
 * These mirror the API's pydantic bounds exactly. The point is not to replace
 * server validation — it is that the person finds out beside the field they are
 * typing in, in words that name the field as the interface labels it, rather
 * than after a round trip in a banner naming a schema field they have never seen.
 */
import { FIELD_LABELS } from './api'

export const RULES = {
  age:                    { min: 3,   max: 30,   label: 'Age', unit: 'years' },
  spherical_equivalent:   { min: -30, max: 15,   label: 'Prescription', unit: 'D' },
  axial_length:           { min: 15,  max: 35,   label: 'Eye length', unit: 'mm',
                            typical: '20–30 mm in a human eye' },
  visual_acuity:          { min: -0.3, max: 2,   label: 'Vision', unit: 'logMAR' },
  corneal_curvature:      { min: 5,   max: 12,   label: 'Corneal curvature', unit: 'mm' },
  parental_myopia:        { min: 0,   max: 2,    label: 'Short-sighted parents', unit: '' },
  screen_time_hours:      { min: 0,   max: 16,   label: 'Screen time', unit: 'h/day' },
  near_work_min:          { min: 0,   max: 720,  label: 'Reading & homework', unit: 'min/day' },
  outdoor_min:            { min: 0,   max: 480,  label: 'Time outdoors', unit: 'min/day' },
  sleep_hours:            { min: 3,   max: 14,   label: 'Sleep', unit: 'h/night' },
  viewing_distance_cm:    { min: 10,  max: 80,   label: 'Screen distance', unit: 'cm' },
  posture_score:          { min: 0,   max: 1,    label: 'Posture', unit: '' },
  continuous_session_min: { min: 5,   max: 240,  label: 'Time before a break', unit: 'min' },
}

/** Returns an error string, or null when the value is acceptable. */
export function checkField(name, value, { required = false } = {}) {
  const rule = RULES[name]
  const label = rule?.label || FIELD_LABELS[name] || name
  if (value === null || value === undefined || value === '') {
    return required ? `${label} is needed.` : null
  }
  const n = Number(value)
  if (Number.isNaN(n)) return `${label} must be a number.`
  if (!rule) return null
  const unit = rule.unit ? ` ${rule.unit}` : ''
  if (n < rule.min) {
    return `${label} must be at least ${rule.min}${unit}.`
      + (rule.typical ? ` Typically ${rule.typical}.` : '')
  }
  if (n > rule.max) {
    return `${label} must be at most ${rule.max}${unit}.`
      + (rule.typical ? ` Typically ${rule.typical}.` : '')
  }
  return null
}

/** Validate a whole form. `required` lists the fields that must be present. */
export function checkForm(values, required = []) {
  const errors = {}
  for (const [name, value] of Object.entries(values)) {
    const err = checkField(name, value, { required: required.includes(name) })
    if (err) errors[name] = err
  }
  for (const name of required) {
    if (values[name] === null || values[name] === undefined || values[name] === '') {
      errors[name] = checkField(name, null, { required: true })
    }
  }
  return errors
}

export const hasErrors = (errors) => Object.keys(errors).length > 0

import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Cohort } from './Clinician'
import ModelCard from './ModelCard'
import { checkField } from '../lib/validate'
import { api } from '../lib/api'
vi.mock('../lib/api', async () => {
  const actual = await vi.importActual('../lib/api')
  return { ...actual, api: { cohort: vi.fn(), modelCard: vi.fn() } }
})

describe('clinician records and model provenance', () => {
  it('offers an empty state without inventing a record', async () => {
    api.cohort.mockResolvedValue([])
    render(<MemoryRouter><Cohort /></MemoryRouter>)
    expect(await screen.findByText('No matching records')).toBeInTheDocument()
  })
  it('filters authorized cohort records', async () => {
    api.cohort.mockResolvedValue([{ patient_id: 'test', external_key: 'fixture-001', n_visits: 2,
      twin_version: 2, latest_se: -1.5, data_source: 'unit-test-fixture', risk_band: null }])
    render(<MemoryRouter><Cohort /></MemoryRouter>)
    expect(await screen.findByRole('link', { name: 'fixture-001' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Search by study key'), { target: { value: 'absent' } })
    expect(screen.getByText('No matching records')).toBeInTheDocument()
  })
  it('shows model loading errors', async () => {
    api.modelCard.mockRejectedValue(new Error('Model unavailable'))
    render(<ModelCard />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Model unavailable')
  })
  it('renders expanded model results when a comparative baseline was not evaluated', async () => {
    api.modelCard.mockResolvedValue({ model_version: 'expanded-fixture', data_source: 'test fixture',
      trained_at: '2026-10-16', limitations: [], metrics: { n_patients: 2, n_visits: 8,
        split: { strategy: 'External cohort', train_patients: 1, val_patients: 1, test_patients: 1 },
        regression: { y_se_12m: { mae: 0.5, rmse: 0.7, r2: 0.2, interval_coverage: 0.8,
          nominal_coverage: 0.9, baselines: { carry_forward: { mae: 0.6 } } } },
      } })
    render(<ModelCard />)
    expect(await screen.findByRole('heading', { name: 'Model card' })).toBeInTheDocument()
    expect(screen.getByRole('row', { name: /se.*12m/i })).toHaveTextContent('Unavailable')
    expect(screen.getByRole('row', { name: /se.*12m/i })).toHaveTextContent('0.6')
  })
  it('shows selectable-month internal and external results with fixed tolerances and patient counts', async () => {
    const result = (mae, rate, patients, tolerance, pairs) => ({ mae, tolerance,
      n_patients: patients, n: pairs, tolerance_hit_rates: { [String(tolerance)]: rate } })
    api.modelCard.mockResolvedValue({ model_version: 'expanded-fixture', limitations: [],
      metrics: { split: { strategy: 'Grouped split', train_patients: 8, val_patients: 3, test_patients: 2 }, regression: {} },
      selectable_horizon_model: { status: 'experimental', request_range_months: [1, 120], metrics: {
        se: { observed_horizons_months: [3, 12, 36], test_by_horizon: { '12.0': result(0.4261, 0.7158, 316, 0.5, 915) },
          external_rels: { by_horizon: { '12.0': result(0.5451, 0.5755, 1901, 0.5, 8758) } } },
        al: { observed_horizons_months: [3, 12, 36], test_by_horizon: { '12.0': result(0.1097, 0.549, 17, 0.1, 51) } },
      } },
    })
    render(<ModelCard />)
    const heading = await screen.findByRole('heading', { name: 'Selectable-month forecast results' })
    const card = within(heading.closest('section'))
    expect(card.getByText('Experimental forecast')).toBeInTheDocument()
    expect(card.getByText(/Available requests: 1–120 months. Observed follow-up: 3–36 months/)).toBeInTheDocument()
    const cells = (label) => within(card.getByRole('row', { name: label })).getAllByRole('cell').map((cell) => cell.textContent)
    expect(cells(/SE · internal test/)).toEqual(['0.426 D', '71.6% within ±0.50 D', '316', '915'])
    expect(cells(/SE · external RELS/)).toEqual(['0.545 D', '57.6% within ±0.50 D', '1901', '8758'])
    expect(cells(/AL · internal test/)).toEqual(['0.110 mm', '54.9% within ±0.10 mm', '17', '51'])
    expect(card.getByText(/Prediction ranges describe uncertainty and do not establish 90% point accuracy/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Fixed-horizon model results' })).toBeInTheDocument()
    expect(screen.queryByText(/^Only 2 test patients/)).not.toBeInTheDocument()
  })
  it('rejects invalid measurements and keeps blanks unknown', () => {
    expect(checkField('axial_length', 99)).toContain('at most')
    expect(checkField('axial_length', null)).toBeNull()
    expect(checkField('axial_length', Infinity)).toContain('must be a number')
  })
})

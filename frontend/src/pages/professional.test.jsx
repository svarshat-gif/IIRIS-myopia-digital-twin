import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
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
  it('rejects invalid measurements and keeps blanks unknown', () => {
    expect(checkField('axial_length', 99)).toContain('at most')
    expect(checkField('axial_length', null)).toBeNull()
    expect(checkField('axial_length', Infinity)).toContain('must be a number')
  })
})

import React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Simulator from './Simulator'
import { api } from '../lib/api'

vi.mock('react-chartjs-2', () => ({ Line: () => <div data-testid="trajectory-chart" /> }))
vi.mock('../lib/api', async () => {
  const actual = await vi.importActual('../lib/api')
  return { ...actual, api: { summary: vi.fn(), twin: vi.fn(), prediction: vi.fn(), quickForecast: vi.fn() } }
})

const forecast = (months, al = null) => ({ horizons: { [`${months}m`]: { horizon_months: months,
  se: { value: -2, lower: -2.5, upper: -1.5, interval_label: 'Estimated range' }, al,
} } })

beforeEach(() => vi.clearAllMocks())

describe('simulator selectable horizons', () => {
  it('forecasts any month from entered clinical values while preserving missing axial length', async () => {
    api.quickForecast.mockImplementation(async (body) => forecast(body.horizon_months))
    render(<MemoryRouter><Simulator publicMode /></MemoryRouter>)
    fireEvent.change(screen.getByRole('spinbutton', { name: /^Age/ }), { target: { value: '10' } })
    fireEvent.change(screen.getByRole('spinbutton', { name: /^Prescription/ }), { target: { value: '-1.5' } })
    fireEvent.click(screen.getByRole('button', { name: 'Show me the forecast' }))
    expect(await screen.findByText('-2.00 D')).toBeInTheDocument()
    expect(screen.getByText('Unavailable for this record.')).toBeInTheDocument()
    expect(api.quickForecast).toHaveBeenLastCalledWith({ age: 10, spherical_equivalent: -1.5, horizon_months: 12 }, expect.any(Object))
    fireEvent.change(screen.getByLabelText('Forecast horizon'), { target: { value: '10' } })
    fireEvent.click(screen.getByRole('button', { name: 'Calculate forecast' }))
    await waitFor(() => expect(api.quickForecast).toHaveBeenLastCalledWith({ age: 10, spherical_equivalent: -1.5, horizon_months: 10 }, expect.any(Object)))
    expect(api.summary).not.toHaveBeenCalled()
    expect(api.twin).not.toHaveBeenCalled()
    fireEvent.change(screen.getByRole('spinbutton', { name: /^Prescription/ }), { target: { value: '-3' } })
    expect(screen.queryByText('-2.00 D')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Forecast horizon')).not.toBeInTheDocument()
  })

  it('uses the personal prediction endpoint at selectable month and year horizons', async () => {
    api.summary.mockResolvedValue({ has_record: true })
    api.twin.mockResolvedValue({ version: 2, history: [{ followup_month: 0, spherical_equivalent: -1.5, axial_length: 24 }] })
    api.prediction.mockImplementation(async (months) => forecast(months, { value: 24.2, lower: 24, upper: 24.4 }))
    render(<MemoryRouter><Simulator /></MemoryRouter>)
    expect(await screen.findByText('-2.00 D')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '5 yr' }))
    await waitFor(() => expect(api.prediction).toHaveBeenLastCalledWith(60, expect.any(Object)))
    expect(await screen.findByText('24.20 mm')).toBeInTheDocument()
    expect(api.quickForecast).not.toHaveBeenCalled()
  })
})

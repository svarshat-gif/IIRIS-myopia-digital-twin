import React from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { horizonMonths, observedTimeline, sortedHorizons } from '../lib/forecast'
import ForecastPanel from './ForecastPanel'
import TrajectoryChart, { trajectoryData } from './TrajectoryChart'
import { Line } from 'react-chartjs-2'

vi.mock('react-chartjs-2', () => ({ Line: vi.fn(() => <div data-testid="trajectory-chart" />) }))

const history = [{ followup_month: 0, visit_date: null, spherical_equivalent: -1, axial_length: 24 },
  { followup_month: 6, visit_date: null, spherical_equivalent: -1.25, axial_length: 24.1 }]
const response = (months, value = -2) => ({ model_version: 'test', horizons: {
  [`${months}m`]: { horizon_months: months,
    se: { value, lower: value - 0.5, upper: value + 0.5, interval_label: 'Estimated range',
      support: { status: 'extrapolated_horizon' } },
    al: { value: 24.5, lower: 24.2, upper: 24.8, interval_label: 'Estimated range' },
  },
} })

describe('month-based forecasts', () => {
  it('converts years to whole months and rejects invalid horizons', () => {
    expect(horizonMonths('2.5', 'years')).toBe(30)
    expect(horizonMonths(String(1 / 12), 'years')).toBe(1)
    expect(horizonMonths('120')).toBe(120)
    for (const value of ['', '0', '-1', '2.1', '121', 'Infinity', 'no']) expect(horizonMonths(value)).toBeNull()
  })

  it('orders dynamic horizons numerically and keeps uneven spacing on a linear axis', () => {
    const prediction = { horizons: { ...response(24).horizons, ...response(1).horizons, ...response(10).horizons } }
    expect(sortedHorizons(prediction).map((entry) => entry.horizon_months)).toEqual([1, 10, 24])
    const data = trajectoryData(history, prediction, null, 'se')
    expect(data.datasets.find((dataset) => dataset.label === 'Expected').data.map((point) => point.x)).toEqual([0, 1, 10, 24])
    expect(data.datasets.find((dataset) => dataset.label === 'Your results').data.map((point) => point.x)).toEqual([-6, 0])
    render(<TrajectoryChart history={history} prediction={prediction} />)
    expect(Line.mock.calls.at(-1)[0].options.scales.x.type).toBe('linear')
    expect(data.datasets[0].label).toBe('Estimated range')
  })

  it('uses relative follow-up months and sorts history without inventing calendar dates', () => {
    expect(observedTimeline([...history].reverse()).points).toEqual([{ x: -6, y: -1 }, { x: 0, y: -1.25 }])
    const unrecordedTimes = [{ visit_date: null, spherical_equivalent: -1 }, { visit_date: null, spherical_equivalent: -2 }]
    expect(observedTimeline(unrecordedTimes).points).toEqual([{ x: 0, y: -2 }])
    expect(observedTimeline([{ visit_date: 'invalid', spherical_equivalent: -2 }]).points).toEqual([{ x: 0, y: -2 }])
  })

  it('calculates an arbitrary month and an equivalent year input', async () => {
    const load = vi.fn(async (months) => response(months))
    render(<ForecastPanel history={history} loadPrediction={load} recordKey="record:1" />)
    expect(await screen.findByText('-2.00 D')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Forecast horizon'), { target: { value: '10' } })
    fireEvent.click(screen.getByRole('button', { name: 'Calculate forecast' }))
    await waitFor(() => expect(load).toHaveBeenLastCalledWith(10, expect.objectContaining({ signal: expect.any(AbortSignal) })))
    await screen.findByText('-2.00 D')
    fireEvent.change(screen.getByLabelText('Time unit'), { target: { value: 'years' } })
    fireEvent.change(screen.getByLabelText('Forecast horizon'), { target: { value: '2.5' } })
    fireEvent.click(screen.getByRole('button', { name: 'Calculate forecast' }))
    await waitFor(() => expect(load).toHaveBeenLastCalledWith(30, expect.any(Object)))
    expect(await screen.findByText('Extrapolated forecast')).toBeInTheDocument()
  })

  it.each([1, 2, 10, 24, 36, 60, 120])('requests exactly %i months through the month control', async (months) => {
    const load = vi.fn(async (value) => response(value))
    render(<ForecastPanel history={history} loadPrediction={load} recordKey="record:1" />)
    await screen.findByText('-2.00 D')
    fireEvent.change(screen.getByLabelText('Forecast horizon'), { target: { value: String(months) } })
    fireEvent.click(screen.getByRole('button', { name: 'Calculate forecast' }))
    await waitFor(() => expect(load).toHaveBeenLastCalledWith(months, expect.any(Object)))
    expect(await screen.findByText('-2.00 D')).toBeInTheDocument()
  })

  it.each([37, 120])('identifies experimental extrapolation at %i months without claiming interval accuracy', async (months) => {
    const load = vi.fn(async (value) => {
      const prediction = response(value)
      prediction.horizons[`${value}m`].se.support.training_max_horizon_months = 36
      return prediction
    })
    render(<ForecastPanel history={history} loadPrediction={load} recordKey="record:1" />)
    expect(screen.getByText('Experimental forecast')).toBeInTheDocument()
    expect(screen.getByText('Estimated ranges describe uncertainty; they do not mean 90% prediction accuracy.')).toBeInTheDocument()
    await screen.findByText('-2.00 D')
    fireEvent.change(screen.getByLabelText('Forecast horizon'), { target: { value: String(months) } })
    fireEvent.click(screen.getByRole('button', { name: 'Calculate forecast' }))
    await screen.findByText('-2.00 D')
    expect(screen.getByText('Extrapolated forecast')).toBeInTheDocument()
    expect(screen.getByText('Beyond measured follow-up of 36 months; accuracy at this horizon has not been established.')).toBeInTheDocument()
    expect(screen.getByText('Estimated range: -2.50 to -1.50 D')).toBeInTheDocument()
  })

  it.each([1, 2])('explains %i-month short-horizon extrapolation outside the measured range', async (months) => {
    const load = vi.fn(async (value) => {
      const prediction = response(value)
      prediction.horizons[`${value}m`].se.support = { status: 'extrapolated_horizon',
        training_min_horizon_months: 3, training_max_horizon_months: 36 }
      return prediction
    })
    render(<ForecastPanel history={history} loadPrediction={load} recordKey="record:1" />)
    await screen.findByText('-2.00 D')
    fireEvent.change(screen.getByLabelText('Forecast horizon'), { target: { value: String(months) } })
    fireEvent.click(screen.getByRole('button', { name: 'Calculate forecast' }))
    await screen.findByText('-2.00 D')
    expect(screen.getByText('Extrapolated forecast')).toBeInTheDocument()
    expect(screen.getByText('Outside measured follow-up range of 3–36 months; accuracy at this horizon has not been established.')).toBeInTheDocument()
    expect(screen.queryByText(/Beyond measured follow-up/)).not.toBeInTheDocument()
  })

  it('hides an old result while loading and ignores late responses for another horizon', async () => {
    const pending = new Map()
    const load = vi.fn((months) => new Promise((resolve) => pending.set(months, resolve)))
    render(<ForecastPanel history={history} loadPrediction={load} recordKey="record:1" />)
    await waitFor(() => expect(pending.has(12)).toBe(true))
    await act(async () => pending.get(12)(response(12, -2)))
    expect(screen.getByText('-2.00 D')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '2 yr' }))
    expect(screen.queryByText('-2.00 D')).not.toBeInTheDocument()
    await waitFor(() => expect(pending.has(24)).toBe(true))
    fireEvent.click(screen.getByRole('button', { name: '3 yr' }))
    await waitFor(() => expect(pending.has(36)).toBe(true))
    await act(async () => pending.get(36)(response(36, -4)))
    await act(async () => pending.get(24)(response(24, -3)))
    expect(screen.getByText('-4.00 D')).toBeInTheDocument()
    expect(screen.queryByText('-3.00 D')).not.toBeInTheDocument()
  })

  it('reports failed forecasts without showing old values, then retries', async () => {
    const load = vi.fn().mockResolvedValueOnce(response(12)).mockRejectedValueOnce(new Error('Forecast unavailable')).mockResolvedValueOnce(response(6, -3))
    render(<ForecastPanel history={history} loadPrediction={load} recordKey="record:1" />)
    await screen.findByText('-2.00 D')
    fireEvent.click(screen.getByRole('button', { name: '6 mo' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Forecast unavailable')
    expect(screen.queryByText('-2.00 D')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('-3.00 D')).toBeInTheDocument()
  })
})

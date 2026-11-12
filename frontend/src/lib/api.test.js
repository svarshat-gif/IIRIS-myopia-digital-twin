import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, token } from './api'

afterEach(() => { vi.unstubAllGlobals(); token.set(null) })

describe('forecast API requests', () => {
  it('sends manual forecasts without authorization and forwards cancellation', async () => {
    token.set('private-session')
    const fetch = vi.fn(async () => ({ ok: true, status: 200, text: async () => '{"horizons":{}}' }))
    vi.stubGlobal('fetch', fetch)
    const controller = new AbortController()
    const body = { age: 10, spherical_equivalent: -1.5, horizon_months: 10 }
    await api.quickForecast(body, { signal: controller.signal })
    const [url, options] = fetch.mock.calls[0]
    expect(url).toBe('/api/v1/simulator/forecast')
    expect(options.method).toBe('POST')
    expect(options.headers).not.toHaveProperty('Authorization')
    expect(JSON.parse(options.body)).toEqual(body)
    expect(options.signal).toBe(controller.signal)
    expect(token.get()).toBe('private-session')
  })

  it('preserves legacy default requests and encodes selected months for authenticated records', async () => {
    token.set('private-session')
    const fetch = vi.fn(async () => ({ ok: true, status: 200, text: async () => '{}' }))
    vi.stubGlobal('fetch', fetch)
    await api.prediction()
    await api.prediction(30)
    await api.patientPrediction('a/b', 10)
    expect(fetch.mock.calls.map(([url]) => url)).toEqual([
      '/api/v1/me/prediction', '/api/v1/me/prediction?horizon_months=30',
      '/api/v1/patients/a%2Fb/prediction?horizon_months=10',
    ])
    expect(fetch.mock.calls[1][1].headers.Authorization).toBe('Bearer private-session')
  })
})

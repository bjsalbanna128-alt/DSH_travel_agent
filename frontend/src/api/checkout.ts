import { travelFetch } from './travel'
import { readApiError } from './adminResources'
import type { CheckoutOptions, VehicleQuote, VehicleSelection } from '../types/checkout'

export const checkoutApi = {
  async vehicleQuote(data: VehicleSelection & { trip_id: string; departure_date: string; product_id?: string },
    signal: AbortSignal): Promise<VehicleQuote> {
    const response = await travelFetch('/api/v1/checkout/vehicle-quote', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
      signal, cache: 'no-store',
    })
    if (!response.ok) throw await readApiError(response)
    return response.json()
  },
  async options(tripId: string, signal: AbortSignal, date?: string): Promise<CheckoutOptions> {
    const query = new URLSearchParams({ trip_id: tripId })
    if (date) query.set('departure_date', date)
    const response = await travelFetch(
      `/api/v1/checkout/options?${query}`, { signal, cache: 'no-store' })
    if (!response.ok) throw await readApiError(response)
    return response.json()
  },
}

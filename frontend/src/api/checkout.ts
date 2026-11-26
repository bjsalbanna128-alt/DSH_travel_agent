import { travelFetch } from './travel'
import { readApiError } from './adminResources'
import type { CheckoutOptions } from '../types/checkout'

export const checkoutApi = {
  async options(tripId: string, signal: AbortSignal, date?: string): Promise<CheckoutOptions> {
    const query = new URLSearchParams({ trip_id: tripId })
    if (date) query.set('departure_date', date)
    const response = await travelFetch(
      `/api/v1/checkout/options?${query}`, { signal, cache: 'no-store' })
    if (!response.ok) throw await readApiError(response)
    return response.json()
  },
}

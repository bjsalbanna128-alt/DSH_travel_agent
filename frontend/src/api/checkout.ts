import { travelFetch } from './travel'
import { readApiError } from './adminResources'
import type { CheckoutOptions } from '../types/checkout'

export const checkoutApi = {
  async options(tripId: string, signal: AbortSignal): Promise<CheckoutOptions> {
    const response = await travelFetch(
      `/api/v1/checkout/options?trip_id=${encodeURIComponent(tripId)}`, { signal, cache: 'no-store' })
    if (!response.ok) throw await readApiError(response)
    return response.json()
  },
}

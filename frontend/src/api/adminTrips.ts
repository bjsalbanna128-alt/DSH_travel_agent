import { adminQueryString, adminRequest } from './adminResources'
import type { PageResult } from '../types/adminResources'
import type { TripDetail, TripSummary, TripVersionDetail } from '../types/adminTrips'

type Query = Parameters<typeof adminQueryString>[0]

const tripPath = (id: string) => `/trips/${encodeURIComponent(id)}`

export const adminTripsApi = {
  trips: (params: Query, signal: AbortSignal) =>
    adminRequest<PageResult<TripSummary>>(`/trips${adminQueryString(params)}`, { signal, cache: 'no-store' }),
  trip: (id: string, signal: AbortSignal) =>
    adminRequest<TripDetail>(tripPath(id), { signal, cache: 'no-store' }),
  version: (id: string, version: number, signal: AbortSignal) =>
    adminRequest<TripVersionDetail>(`${tripPath(id)}/versions/${version}`, { signal, cache: 'no-store' }),
}

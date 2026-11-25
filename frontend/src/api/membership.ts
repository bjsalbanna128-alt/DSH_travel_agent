import { adminQueryString, adminRequest, readApiError } from './adminResources'
import { travelFetch } from './travel'
import type { PageResult } from '../types/adminResources'
import type { MemberDetail, MemberProfile, MemberSummary, PointEntry, PointOverview, Traveler } from '../types/membership'

type Query = Parameters<typeof adminQueryString>[0]
const memberPath = (id: string) => `/members/${encodeURIComponent(id)}`
const travelerPath = (id: string) => `/travelers/${encodeURIComponent(id)}`

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await travelFetch(`/api/v1/members${path}`, { cache: 'no-store', ...options })
  if (!response.ok) throw await readApiError(response)
  return response.status === 204 ? undefined as T : response.json()
}

function payload(method: 'POST' | 'PATCH', data: object, signal: AbortSignal) {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data), signal }
}

export const membershipApi = {
  profile: (signal: AbortSignal) => request<MemberProfile>('/profile', { signal }),
  saveProfile: (data: object, signal: AbortSignal) => request<MemberProfile>('/profile', payload('PATCH', data, signal)),
  travelers: (signal: AbortSignal) => request<Traveler[]>('/travelers', { signal }),
  addTraveler: (data: object, signal: AbortSignal) => request<Traveler>('/travelers', payload('POST', data, signal)),
  editTraveler: (id: string, data: object, signal: AbortSignal) =>
    request<Traveler>(travelerPath(id), payload('PATCH', data, signal)),
  deleteTraveler: (id: string, signal: AbortSignal) =>
    request<void>(travelerPath(id), { method: 'DELETE', signal }),
  points: (signal: AbortSignal) => request<PointOverview>('/points', { signal }),
  myLedger: (params: Query, signal: AbortSignal) =>
    request<PageResult<PointEntry>>(`/point-transactions${adminQueryString(params)}`, { signal }),

  members: (params: Query, signal: AbortSignal) =>
    adminRequest<PageResult<MemberSummary>>(`/members${adminQueryString(params)}`, { signal, cache: 'no-store' }),
  member: (id: string, signal: AbortSignal) =>
    adminRequest<MemberDetail>(memberPath(id), { signal, cache: 'no-store' }),
  memberLedger: (id: string, params: Query, signal: AbortSignal) =>
    adminRequest<PageResult<PointEntry>>(`${memberPath(id)}/point-transactions${adminQueryString(params)}`,
      { signal, cache: 'no-store' }),
}

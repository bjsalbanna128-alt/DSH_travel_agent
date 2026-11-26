import { adminQueryString, adminRequest, readApiError } from './adminResources'
import { travelFetch } from './travel'
import type { OrderDetail, OrderPage } from '../types/orders'

type Query = Parameters<typeof adminQueryString>[0]

async function tourist<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await travelFetch(`/api/v1/orders${path}`, { cache: 'no-store', ...options })
  if (!response.ok) throw await readApiError(response)
  return response.json()
}

function payload(method: 'POST', data: object, signal?: AbortSignal) {
  return {
    method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data), signal,
  }
}

export const ordersApi = {
  create: (data: Record<string, unknown>, idempotencyKey: string) =>
    tourist<OrderDetail>('', {
      ...payload('POST', data),
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
    }),
  mine: (params: Query, signal: AbortSignal) =>
    tourist<OrderPage>(`${adminQueryString(params)}`, { signal }),
  detail: (id: string, signal: AbortSignal) =>
    tourist<OrderDetail>(`/${encodeURIComponent(id)}`, { signal }),
  pay: (id: string, idempotencyKey: string) =>
    tourist<OrderDetail>(`/${encodeURIComponent(id)}/payments`,
      payload('POST', { idempotency_key: idempotencyKey })),
  cancel: (id: string, reason: string) =>
    tourist<OrderDetail>(`/${encodeURIComponent(id)}/cancel`, payload('POST', { reason })),
  requestCancel: (id: string, reason: string) =>
    tourist<OrderDetail>(`/${encodeURIComponent(id)}/cancel-request`, payload('POST', { reason })),

  queue: (params: Query, signal: AbortSignal) =>
    adminRequest<OrderPage>(`/orders${adminQueryString(params)}`, { signal, cache: 'no-store' }),
  adminDetail: (id: string, signal: AbortSignal) =>
    adminRequest<OrderDetail>(`/orders/${encodeURIComponent(id)}`, { signal, cache: 'no-store' }),
  approve: (id: string, note: string) =>
    adminRequest<OrderDetail>(`/orders/${encodeURIComponent(id)}/approve`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ note }),
    }),
  reject: (id: string, reason: string) =>
    adminRequest<OrderDetail>(`/orders/${encodeURIComponent(id)}/reject`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reason }),
    }),
  resolveCancel: (id: string, approve: boolean, note: string) =>
    adminRequest<OrderDetail>(`/orders/${encodeURIComponent(id)}/cancel-request`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approve, note }),
    }),
  sweep: () =>
    adminRequest<{ expired: number; refunds: number }>('/orders/sweep', { method: 'POST' }),
}

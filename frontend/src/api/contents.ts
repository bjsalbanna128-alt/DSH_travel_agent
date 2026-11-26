import { adminQueryString, adminRequest } from './adminResources'
import type { ContentFields, ContentPage, ContentRecord, SyncResult } from '../types/contents'

type Query = Parameters<typeof adminQueryString>[0]

const path = (id: string) => `/contents/${encodeURIComponent(id)}`

export const contentsApi = {
  list: (params: Query, signal: AbortSignal) =>
    adminRequest<ContentPage>(`/contents${adminQueryString(params)}`, { signal, cache: 'no-store' }),
  get: (id: string, signal: AbortSignal) =>
    adminRequest<ContentRecord>(path(id), { signal, cache: 'no-store' }),
  create: (data: ContentFields) =>
    adminRequest<ContentRecord>('/contents', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
    }),
  update: (id: string, data: Partial<ContentFields>) =>
    adminRequest<ContentRecord>(path(id), {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
    }),
  publish: (id: string) => adminRequest<ContentRecord>(`${path(id)}/publish`, { method: 'POST' }),
  unpublish: (id: string) => adminRequest<ContentRecord>(`${path(id)}/unpublish`, { method: 'POST' }),
  bindProducts: (id: string, productIds: string[]) =>
    adminRequest<ContentRecord>(`${path(id)}/products`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_ids: productIds }),
    }),
  remove: (id: string) => adminRequest<void>(path(id), { method: 'DELETE' }),
  syncVectors: (rebuild: boolean) =>
    adminRequest<SyncResult>(`/contents/sync-vectors?rebuild=${rebuild}`, { method: 'POST' }),
  vectorStatus: (signal?: AbortSignal) =>
    adminRequest<{ pending: boolean; failed: boolean }>('/contents/vector-status', { signal }),
}

import router, { operatorDeniedDestination } from '../router'
import { useAuthStore } from '../stores/auth'
import type {
  OfferDay, OfferPage, OfferValues, PageResult, PoiKind, PoiReference,
  Product, ProductFields, ProductStatus, Supplier, SupplierFields, SupplierStatus,
} from '../types/adminResources'
import { travelFetch } from './travel'

type Query = Record<string, string | number | undefined>

export interface ApiFieldIssue {
  path: (string | number)[]
  message: string
}

export class AdminRequestError extends Error {
  conflicts: { product_id?: string; service_date?: string; reason: string }[] = []
  readonly dates: string[]
  readonly issues: ApiFieldIssue[]
  readonly status: number

  constructor(message: string, dates: string[], issues: ApiFieldIssue[], status: number) {
    super(message)
    this.dates = dates
    this.issues = issues
    this.status = status
  }
}

export function adminError(error: unknown): string {
  return error instanceof Error ? error.message : '操作失败，请重试。'
}

async function request<T>(path: string, init?: RequestInit, { redirectOnForbidden = true } = {}): Promise<T> {
  const auth = useAuthStore()
  const version = auth.sessionVersion
  const res = await travelFetch(`/api/v1/admin${path}`, init)
  if (redirectOnForbidden && res.status === 403 && version === auth.sessionVersion && !init?.signal?.aborted) {
    void auth.syncSession(true)
    void router.replace(operatorDeniedDestination())
  }
  if (!res.ok) throw await readApiError(res)
  return res.status === 204 ? undefined as T : res.json()
}

export async function readApiError(res: Response): Promise<AdminRequestError> {
  const { detail } = await res.json().catch(() => ({}))
  const validation: ApiFieldIssue[] = Array.isArray(detail)
    ? detail.map(item => ({ path: item.loc ?? [], message: item.msg })) : []
  const message = typeof detail === 'string' ? detail
    : typeof detail?.message === 'string'
      ? detail.message + (Array.isArray(detail.missing) && detail.missing.length
        && !detail.missing.every((label: string) => detail.message.includes(label))
        ? `（${detail.missing.join('、')}）` : '')
      : validation.length ? validation.map(issue => `${issue.path.at(-1)}：${issue.message}`).join('；')
    : `请求失败（${res.status}），请重试。`
  const failure = new AdminRequestError(
    message, Array.isArray(detail?.dates) ? detail.dates : [],
    Array.isArray(detail?.errors) ? detail.errors : validation, res.status,
  )
  if (Array.isArray(detail?.items)) failure.conflicts = detail.items
  return failure
}

function query(params: Query): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.set(key, String(value))
  }
  return search.size ? `?${search}` : ''
}

function write<T>(path: string, method: 'POST' | 'PATCH', body: object) {
  return request<T>(path, {
    method, body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' },
  })
}

export { request as adminRequest, query as adminQueryString }

const supplierPath = (id: string) => `/suppliers/${encodeURIComponent(id)}`
const productPath = (id: string) => `/products/${encodeURIComponent(id)}`
const offersPath = (id: string) => `${productPath(id)}/offers`

export const adminResources = {
  suppliers: (params: Query, signal?: AbortSignal) =>
    request<PageResult<Supplier>>(`/suppliers${query(params)}`, { signal }),
  supplier: (id: string, signal?: AbortSignal) => request<Supplier>(supplierPath(id), { signal }),
  createSupplier: (data: SupplierFields) => write<Supplier>('/suppliers', 'POST', data),
  updateSupplier: (id: string, data: Partial<SupplierFields & { status: SupplierStatus }>) =>
    write<Supplier>(supplierPath(id), 'PATCH', data),
  deleteSupplier: (id: string) => request<void>(supplierPath(id), { method: 'DELETE' }),

  products: (params: Query, signal?: AbortSignal) =>
    request<PageResult<Product>>(`/products${query(params)}`, { signal }),
  product: (id: string, signal?: AbortSignal) => request<Product>(productPath(id), { signal }),
  createProduct: (data: ProductFields) => write<Product>('/products', 'POST', data),
  updateProduct: (id: string, data: Partial<ProductFields & { status: ProductStatus }>) =>
    write<Product>(productPath(id), 'PATCH', data),
  deleteProduct: (id: string) => request<void>(productPath(id), { method: 'DELETE' }),

  pois: (city: string, keyword: string, type: PoiKind, signal?: AbortSignal) =>
    request<{ items: PoiReference[]; warning: string | null }>(`/pois${query({ city, keyword, type })}`, { signal }),

  offers: (id: string, params: Query, signal?: AbortSignal) =>
    request<OfferPage>(`${offersPath(id)}${query(params)}`, { signal }),
  createOffer: (id: string, data: OfferValues & { service_date: string }) =>
    write<OfferDay>(offersPath(id), 'POST', data),
  updateOffer: (id: string, date: string, data: Partial<OfferValues>) =>
    write<OfferDay>(`${offersPath(id)}/${encodeURIComponent(date)}`, 'PATCH', data),
  deleteOffer: (id: string, date: string) =>
    request<void>(`${offersPath(id)}/${encodeURIComponent(date)}`, { method: 'DELETE' }),
  batchOffers: (id: string, data: OfferValues & { start_date: string; end_date: string; overwrite: boolean }) =>
    write<{ created: number; updated: number }>(`${offersPath(id)}/batch`, 'POST', data),
}

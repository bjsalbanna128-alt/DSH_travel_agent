import type { PageResult } from '../types/adminResources'
import type {
  PublishedRecommendation, RecommendationDraft, RecommendationFields,
} from '../types/recommendations'
import { adminQueryString, adminRequest, readApiError } from './adminResources'
import { travelFetch } from './travel'

const adminPath = '/recommendations'
const draftPath = (id: string) => `${adminPath}/${encodeURIComponent(id)}`

function write(path: string, method: 'POST' | 'PUT', body: object) {
  return adminRequest<RecommendationDraft>(path, {
    method, body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' },
  })
}

export const adminRecommendations = {
  list: (params: Parameters<typeof adminQueryString>[0], signal?: AbortSignal) =>
    adminRequest<PageResult<RecommendationDraft>>(`${adminPath}${adminQueryString(params)}`, { signal }),
  get: (id: string, signal?: AbortSignal) => adminRequest<RecommendationDraft>(draftPath(id), { signal }),
  create: (fields: RecommendationFields) => write(adminPath, 'POST', fields),
  save: (id: string, revision: number, fields: RecommendationFields) =>
    write(`${draftPath(id)}/draft`, 'PUT', { ...fields, expected_revision: revision }),
  upload: (id: string, revision: number, file: File) =>
    adminRequest<RecommendationDraft>(`${draftPath(id)}/draft/cover?expected_revision=${revision}`, {
      method: 'PUT', body: file,
    }),
  publish: (id: string, revision: number) =>
    write(`${draftPath(id)}/publish`, 'POST', { expected_revision: revision }),
  unpublish: (id: string, revision: number) =>
    write(`${draftPath(id)}/unpublish`, 'POST', { expected_revision: revision }),
}

export async function fetchRecommendations(signal: AbortSignal): Promise<PublishedRecommendation[]> {
  const response = await travelFetch('/api/v1/recommendations', { signal, cache: 'no-store' })
  if (!response.ok) throw await readApiError(response)
  return response.json()
}

export async function fetchRecommendationCover(path: string, signal: AbortSignal): Promise<Blob> {
  if (!/^\/api\/v1\/(?:admin\/)?recommendations\//.test(path)) throw new Error('封面地址无效')
  const response = await travelFetch(path, { signal, cache: 'no-store' })
  if (!response.ok) throw await readApiError(response)
  return response.blob()
}

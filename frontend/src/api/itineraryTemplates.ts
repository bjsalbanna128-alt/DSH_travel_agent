import { adminQueryString, adminRequest, readApiError } from './adminResources'
import { travelFetch } from './travel'
import type { PageResult } from '../types/adminResources'
import type { PublishedTemplate, ReaderTemplateSummary, TemplateDetail, TemplateDraft, TemplateSummary, TemplateVisibility } from '../types/itineraryTemplates'

const base = '/itinerary-templates'
const path = (id: string) => `${base}/${encodeURIComponent(id)}`

function write(url: string, method: 'POST' | 'PUT', data: object) {
  return adminRequest<TemplateDetail>(url, {
    method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  })
}

export const itineraryTemplates = {
  list: (params: { title: string; destination: string; visibility: TemplateVisibility | ''; page: number }, signal: AbortSignal) =>
    adminRequest<PageResult<TemplateSummary>>(`${base}${adminQueryString(params)}`, { signal, cache: 'no-store' }),
  get: (id: string, signal: AbortSignal) => adminRequest<TemplateDetail>(path(id), { signal, cache: 'no-store' }),
  create: (draft: TemplateDraft) => write(base, 'POST', draft),
  save: (id: string, expected_revision: number, draft: TemplateDraft) =>
    write(`${path(id)}/draft`, 'PUT', { expected_revision, draft }),
  publish: (id: string, expected_revision: number) => write(`${path(id)}/publish`, 'POST', { expected_revision }),
  unpublish: (id: string, expected_revision: number) => write(`${path(id)}/unpublish`, 'POST', { expected_revision }),
  async getPublished(id: string, signal: AbortSignal): Promise<PublishedTemplate> {
    const response = await travelFetch(`/api/v1${path(id)}`, { signal, cache: 'no-store' })
    if (!response.ok) throw await readApiError(response)
    return response.json()
  },
  async listPublished(
    params: { page?: number; page_size?: number }, signal: AbortSignal,
  ): Promise<PageResult<ReaderTemplateSummary>> {
    const response = await travelFetch(`/api/v1${base}${adminQueryString(params)}`, { signal, cache: 'no-store' })
    if (!response.ok) throw await readApiError(response)
    return response.json()
  },
}

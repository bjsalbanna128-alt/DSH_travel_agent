import type { PageResult } from '../types/adminResources'
import type {
  AdminTicketDetail, AdminTicketPage, InboxMessage, InboxMessageDetail, MessageCode, MessageSetting,
  NewTicket, TicketDetail, TicketPriority, TicketSummary,
} from '../types/support'
import { adminQueryString, adminRequest, readApiError } from './adminResources'
import { travelFetch } from './travel'

type Query = Parameters<typeof adminQueryString>[0]
type Count = { unread_count: number }
type MarkedRead = Count & { message: InboxMessageDetail }
const ticketPath = (id: string) => `/tickets/${encodeURIComponent(id)}`
const messagePath = (id: string) => `/messages/${encodeURIComponent(id)}`

async function request<T>(operator: boolean, path: string, init?: RequestInit, options?: { redirectOnForbidden?: boolean }): Promise<T> {
  const fetchOptions = { ...init, cache: 'no-store' as const }
  if (operator) return adminRequest<T>(path, fetchOptions, options)
  const response = await travelFetch(`/api/v1${path}`, fetchOptions)
  if (!response.ok) throw await readApiError(response)
  return response.json()
}

function payload(method: 'POST' | 'PATCH', body: object, signal?: AbortSignal): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal }
}

export const supportApi = {
  inbox: (operator: boolean, page: number, unreadOnly: boolean, signal?: AbortSignal) =>
    request<PageResult<InboxMessage>>(operator, `/messages${adminQueryString({ page, unread_only: unreadOnly ? 'true' : undefined })}`, { signal }),
  unread: (operator: boolean, signal?: AbortSignal) => request<Count>(operator, '/messages/unread-count', { signal }),
  message: (operator: boolean, id: string, signal?: AbortSignal) =>
    request<InboxMessageDetail>(operator, messagePath(id), { signal }),
  read: (operator: boolean, id: string, signal?: AbortSignal) =>
    request<MarkedRead>(operator, `${messagePath(id)}/read`, { method: 'POST', signal }),

  settings: (signal?: AbortSignal) => request<MessageSetting[]>(true, '/message-settings', { signal }),
  setEnabled: (code: MessageCode, revision: number, enabled: boolean, signal?: AbortSignal) =>
    request<MessageSetting>(true, `/message-settings/${encodeURIComponent(code)}`,
      payload('PATCH', { enabled, expected_revision: revision }, signal)),

  myTickets: (page: number, signal?: AbortSignal) =>
    request<PageResult<TicketSummary>>(false, `/tickets${adminQueryString({ page })}`, { signal }),
  submit: (body: NewTicket, signal?: AbortSignal) => request<TicketDetail>(false, '/tickets', payload('POST', body, signal)),
  myTicket: (id: string, signal?: AbortSignal) => request<TicketDetail>(false, ticketPath(id), { signal }),
  adminTickets: (filters: Query, signal?: AbortSignal) =>
    request<AdminTicketPage>(true, `/tickets${adminQueryString(filters)}`, { signal }),
  adminTicket: (id: string, signal?: AbortSignal) => request<AdminTicketDetail>(true, ticketPath(id), { signal }),
  ticketAction: (id: string, action: 'claim' | 'reopen' | 'close', revision: number, result?: string, signal?: AbortSignal) =>
    request<AdminTicketDetail>(true, `${ticketPath(id)}/${action}`,
      payload('POST', { expected_revision: revision, result }, signal), { redirectOnForbidden: false }),
  setPriority: (id: string, revision: number, priority: TicketPriority, signal?: AbortSignal) =>
    request<AdminTicketDetail>(true, `${ticketPath(id)}/priority`,
      payload('PATCH', { priority, expected_revision: revision }, signal), { redirectOnForbidden: false }),
}

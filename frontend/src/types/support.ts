import type { PageResult } from './adminResources'

export type MessageCode = 'trip.confirmed' | 'ticket.created' | 'ticket.closed'
export type MessageTarget = 'trip_confirmation' | 'admin_ticket' | 'tourist_ticket'
export type TicketCategory = 'inquiry' | 'complaint' | 'suggestion'
export type TicketStatus = 'new' | 'processing' | 'closed'
export type TicketPriority = 'low' | 'normal' | 'high'

export const categoryLabels: Record<TicketCategory, string> = { inquiry: '咨询', complaint: '投诉', suggestion: '建议' }
export const ticketStatusLabels: Record<TicketStatus, string> = { new: '待处理', processing: '处理中', closed: '已关闭' }
export const priorityLabels: Record<TicketPriority, string> = { low: '低', normal: '普通', high: '高' }

export interface InboxMessage {
  id: string
  code: MessageCode
  title: string
  body: string
  target_type: MessageTarget
  target_id: string
  target_version: number | null
  sent_at: string
  read_at: string | null
}

export interface InboxMessageDetail extends InboxMessage {
  confirmation: { trip_id: string; title: string; version: number; confirmed_at: string } | null
}

export interface MessageSetting {
  code: MessageCode
  name: string
  trigger: string
  audience: string
  channel: 'in_app'
  enabled: boolean
  revision: number
  updated_by: string | null
  updated_by_name: string | null
  updated_at: string | null
}

export interface AccountLabel {
  id: string
  username: string
}

export interface TicketSummary {
  id: string
  number: string
  category: TicketCategory
  subject: string
  status: TicketStatus
  created_at: string
  updated_at: string
}

export interface TicketHandling {
  round: number
  result: string | null
  completed_at: string | null
}

export interface TicketDetail extends TicketSummary {
  content: string
  handlings: TicketHandling[]
}

export interface AdminTicketSummary extends TicketSummary {
  priority: TicketPriority
  revision: number
  submitter: AccountLabel
  assignee: AccountLabel | null
}

export interface AdminTicketHandling extends TicketHandling {
  handler_id: string
  handler_name: string
  claimed_at: string
  completed_by: string | null
}

export interface AdminTicketDetail extends TicketDetail, AdminTicketSummary {
  order_id: string | null
  handlings: AdminTicketHandling[]
}

export interface AdminTicketPage extends PageResult<AdminTicketSummary> {
  assignees: AccountLabel[]
}

export interface NewTicket {
  category: TicketCategory
  subject: string
  content: string
}

const dateTime = new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'medium' })
export function supportTime(value?: string | null) {
  if (!value) return '—'
  const date = new Date(/Z$|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`)
  return dateTime.format(date)
}

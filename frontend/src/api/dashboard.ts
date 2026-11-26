import { adminRequest } from './adminResources'
import type { TicketCategory } from '../types/support'

export interface AdminDashboard {
  as_of: string
  overview: {
    confirmed_trips: number
    tourist_members: number
    new_members_today: number
    templates_total: number
    templates_published: number
    recommendations_total: number
    recommendations_published: number
  }
  work: {
    unassigned_tickets: number
    my_processing_tickets: number
    high_unassigned_tickets: number
    my_unread_messages: number
    new_tickets_today: number
  }
  high_priority_items: { id: string; number: string; category: TicketCategory; created_at: string }[]
}

export function getDashboard(signal: AbortSignal) {
  return adminRequest<AdminDashboard>('/dashboard', { signal, cache: 'no-store' })
}

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

export type ProductType = 'hotel_room' | 'attraction_ticket' | 'vehicle'

export interface TrendPoint {
  date: string
  paid_fen: number
  refund_fen: number
  net_fen: number
  orders: number
  avg_order_fen: number
  fulfillment_total: number
  fulfillment_ready: number
  fleet_used: number
  fleet_capacity: number
}

export interface AdminTrends {
  days: 7 | 30
  from: string
  to: string
  today: string
  as_of: string
  series: TrendPoint[]
  totals: {
    paid_fen: number
    refund_fen: number
    net_fen: number
    orders: number
    avg_order_fen: number
    fulfillment_total: number
    fleet_used: number
  }
  by_category: { product_type: ProductType; amount_fen: number }[]
}

export function getDashboardTrends(days: 7 | 30, signal: AbortSignal) {
  return adminRequest<AdminTrends>(`/dashboard/trends?days=${days}`, { signal, cache: 'no-store' })
}

export function formatYuan(fen: number): string {
  const value = fen / 100
  return `¥${value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

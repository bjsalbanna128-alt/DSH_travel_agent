export type OrderStatus =
  | 'pending_payment' | 'paid_pending_review' | 'confirmed' | 'cancel_requested' | 'cancelled' | 'completed'

export type FundStatus = 'unpaid' | 'processing' | 'paid' | 'refunding' | 'refunded' | 'refund_failed'

export const orderStatusLabels: Record<OrderStatus, string> = {
  pending_payment: '待支付', paid_pending_review: '已付款 · 待确认', confirmed: '已确认',
  cancel_requested: '取消申请中', cancelled: '已取消', completed: '已完成',
}

export const fundStatusLabels: Record<FundStatus, string> = {
  unpaid: '未收款', processing: '支付处理中', paid: '已收款',
  refunding: '退款中', refunded: '已退款', refund_failed: '退款失败待重试',
}

export interface OrderItemView {
  id: string
  product_id: string
  product_name: string
  product_type: string
  attributes: Record<string, unknown>
  service_date: string
  quantity: number
  unit_sale_fen: number
  subtotal_sale_fen: number
}

export interface OrderTravelerView {
  name: string
  document_type: string
  document_mask: string
  phone_mask: string
  is_lead: boolean
}

export interface OrderEventView {
  kind: string
  from_status: string | null
  to_status: string | null
  actor_name: string | null
  reason: string
  created_at: string
}

export interface OrderPaymentView {
  id: string
  provider: string
  amount_fen: number
  event_id: string
  paid_at: string
}

export interface OrderRefundView {
  id: string
  refund_no: string
  amount_fen: number
  status: string
  attempts: number
  last_error: string
  processed_at: string | null
}

export interface OrderSummary {
  id: string
  order_no: string
  status: OrderStatus
  fund_status: FundStatus
  total_sale_fen: number
  expires_at: string
  created_at: string
  waiting_minutes: number
  review_overdue?: boolean
}

export interface TouristOrderDetail extends OrderSummary {
  trip_id: string | null
  departure_date: string | null
  contact_name: string
  contact_phone: string
  cancelled_at: string | null
  server_time: string
  after_sales_ticket_id: string | null
  items: OrderItemView[]
  travelers: OrderTravelerView[]
  events: Omit<OrderEventView, 'actor_name' | 'reason'>[]
  payments: OrderPaymentView[]
  refunds: Omit<OrderRefundView, 'attempts' | 'last_error'>[]
}

export interface OrderDetail extends TouristOrderDetail {
  user_id: string
  total_cost_fen: number
  review_note: string
  cancel_reason: string
  events: OrderEventView[]
  refunds: OrderRefundView[]
}

export interface OrderPage {
  items: OrderSummary[]
  total: number
}

export const formatFen = (fen: number) => `¥${(fen / 100).toLocaleString(undefined, { minimumFractionDigits: 2 })}`

export const orderTime = (value: string | null) => {
  if (!value) return '—'
  const date = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value}Z`)
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Shanghai',
  }).format(date)
}

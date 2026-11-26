import { adminQueryString, adminRequest } from './adminResources'

export type TaskStatus = 'pending' | 'ready' | 'in_progress' | 'completed' | 'exception' | 'cancelled'
export type TaskType = 'hotel_checkin' | 'ticket_entry' | 'vehicle_pickup' | 'vehicle_charter' | 'other'

export const taskStatusLabels: Record<TaskStatus, string> = {
  pending: '待处理', ready: '已就绪', in_progress: '进行中',
  completed: '已完成', exception: '异常', cancelled: '已作废',
}

export const taskTypeLabels: Record<TaskType, string> = {
  hotel_checkin: '酒店入住', ticket_entry: '景点入园',
  vehicle_pickup: '接机', vehicle_charter: '包车', other: '其他',
}

export interface TaskSummary {
  id: string
  order_id: string
  task_type: TaskType
  service_date: string
  start_time: string | null
  product_name: string
  quantity: number
  status: TaskStatus
  supplier_name: string
  version: number
}

export interface TaskEvent {
  kind: string
  from_status: string | null
  to_status: string | null
  actor_name: string | null
  reason: string
  created_at: string
}

export interface TaskDetail extends TaskSummary {
  order_item_id: string
  location_name: string
  voucher_no: string
  confirmation_no: string
  notes: string
  exception_reason: string
  started_at: string | null
  completed_at: string | null
  assignment: { vehicle_id: string; driver_id: string; assigned_by_name: string; assigned_at: string } | null
  events: TaskEvent[]
}

export interface ResourceOption {
  id: string
  name?: string
  plate_no?: string
  model_name?: string
  seats?: number
  license_type?: string
}

export interface Board {
  today: string
  by_status: Record<string, number>
  per_day: { date: string; total: number; ready: number; in_progress: number; pending: number }[]
  exceptions: { id: string; task_type: TaskType; service_date: string; reason: string }[]
  total: number
}

type Query = Parameters<typeof adminQueryString>[0]

const path = (id: string) => `/fulfillment/${encodeURIComponent(id)}`

function post<T>(url: string, body: object = {}): Promise<T> {
  return adminRequest<T>(url, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
}

export const fulfillmentApi = {
  tasks: (params: Query, signal?: AbortSignal) =>
    adminRequest<{ items: TaskSummary[]; total: number }>(`/fulfillment${adminQueryString(params)}`,
      { signal, cache: 'no-store' }),
  task: (id: string, signal?: AbortSignal) =>
    adminRequest<TaskDetail>(path(id), { signal, cache: 'no-store' }),
  confirm: (id: string, data: { voucher_no?: string; confirmation_no?: string; expected_version: number }) =>
    post<TaskDetail>(`${path(id)}/confirm`, data),
  start: (id: string, expected_version: number) => post<TaskDetail>(`${path(id)}/start`, { expected_version }),
  complete: (id: string, expected_version: number) => post<TaskDetail>(`${path(id)}/complete`, { expected_version }),
  exception: (id: string, reason: string, expected_version: number) =>
    post<TaskDetail>(`${path(id)}/exception`, { reason, expected_version }),
  recover: (id: string, expected_version: number) => post<TaskDetail>(`${path(id)}/recover`, { expected_version }),
  cancel: (id: string, reason: string, expected_version: number) =>
    post<TaskDetail>(`${path(id)}/cancel`, { reason, expected_version }),
  candidates: (id: string, signal?: AbortSignal) =>
    adminRequest<{ vehicles: ResourceOption[]; drivers: ResourceOption[] }>(`${path(id)}/candidates`,
      { signal, cache: 'no-store' }),
  assign: (id: string, vehicle_id: string, driver_id: string, expected_version: number) =>
    post<TaskDetail>(`${path(id)}/assign`, { vehicle_id, driver_id, expected_version }),
  release: (id: string, expected_version: number) => post<TaskDetail>(`${path(id)}/release`, { expected_version }),
  board: (days: number, signal?: AbortSignal) =>
    adminRequest<Board>(`/fulfillment/board?days=${days}`, { signal, cache: 'no-store' }),
}

export const formatTime = (value: string | null | undefined) => {
  if (!value) return '—'
  const date = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value}Z`)
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Shanghai',
  }).format(date)
}

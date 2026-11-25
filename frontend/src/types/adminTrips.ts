import type { Itinerary } from './travel'

export interface TripVersionSummary {
  version: number
  description: string
  created_at: string | null
  is_current: boolean
  is_confirmed: boolean
}

export interface TripSummary {
  id: string
  username: string
  title: string
  destination: string
  duration_days: number
  budget_total: number
  version: number
  confirmed_version: number | null
  created_at: string | null
  updated_at: string | null
}

export interface TripDetail extends TripSummary {
  status: string
  travel_request: Record<string, unknown>
  itinerary: Itinerary
  versions: TripVersionSummary[]
}

export interface TripVersionDetail {
  trip_id: string
  version: number
  description: string
  created_at: string | null
  is_current: boolean
  is_confirmed: boolean
  itinerary: Itinerary
}

// Trip timestamps are stored as naive UTC; mark them as UTC before formatting.
function asUtc(value: string): Date {
  const hasZone = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(value)
  return new Date(hasZone ? value : `${value}Z`)
}

const formatter = new Intl.DateTimeFormat('zh-CN', {
  dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Shanghai',
})

export const tripTime = (value: string | null | undefined) => value ? formatter.format(asUtc(value)) : '—'

export const confirmedLabel = (value: number | null | undefined) =>
  value === null || value === undefined ? '未记录（该功能上线前确认）' : `v${value}`

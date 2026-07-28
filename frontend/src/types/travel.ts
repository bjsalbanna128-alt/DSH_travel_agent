// ═══════════════════════════════════════════════════════
// Travel Planner — TypeScript Type Definitions
// ═══════════════════════════════════════════════════════

export interface TravelRequest {
  destination: string
  days: number
  budget: { total_cny: number; per_day_cny: number }
  travelers: { adults: number; children: number; elderly: number }
  preferences: string[]
  special_requirements: string[]
  departure_city: string
  travel_time: string
  pace: 'relaxed' | 'moderate' | 'intensive'
}

export interface Location {
  lat: number
  lng: number
}

export interface Attraction {
  id: string
  name: string
  category: string
  description: string
  rating: number
  visit_duration_hours: number
  ticket_price_cny: number
  location: Location
  opening_hours: string
  tags: string[]
  suitable_for: string[]
  recommended_reason: string
}

export interface Route {
  day: number
  attraction_ids: string[]
  total_distance_km: number
  travel_mode: string
  estimated_travel_time_minutes: number
  constraint_violations: string[]
}

export interface Hotel {
  id: string
  name: string
  area: string
  price_per_night_cny: number
  rating: number
  location: Location
  amenities: string[]
  description: string
  booking_url: string
}

export interface Restaurant {
  id: string
  name: string
  cuisine: string
  area: string
  avg_price_per_person_cny: number
  rating: number
  location: Location
  must_try_dishes: string[]
  description: string
}

export interface TransportOption {
  type: string
  from_location: string
  to_location: string
  departure_time: string
  arrival_time: string
  price_cny: number
  booking_url: string
}

export interface TransportPlan {
  intercity: TransportOption[]
  intraday: TransportOption[][]
}

export interface DayPlan {
  day: number
  date: string
  attractions: Attraction[]
  route: Route | null
  lunch: Restaurant | null
  dinner: Restaurant | null
  hotel: Hotel | null
  transport: TransportOption[]
  notes: string
}

export interface Itinerary {
  title: string
  destination: string
  duration_days: number
  total_budget_estimate_cny: number
  day_plans: DayPlan[]
  overall_tips: string
  version: number
  created_at: string
}

export interface ApprovalRequest {
  approval_id: string
  type: string
  question: string
  options: string[]
  data: Itinerary
}

export interface AgentProgress {
  agent_name: string
  status: 'pending' | 'running' | 'done' | 'failed'
  message: string
}

export interface ProgressInfo {
  overall_percent: number
  current_phase: string
  agents: AgentProgress[]
  is_streaming: boolean
}

export interface ChatMessage {
  id: string
  role: 'user' | 'agent' | 'system'
  content: string
  timestamp: string
}

export interface VersionInfo {
  version: number
  created_at: string
  description: string
}

export interface SSECallbacks {
  onAgentStart?: (agent: string, display: string, progress: number) => void
  onAgentDone?: (agent: string, summary: string, progress: number, data?: any) => void
  onToken?: (agent: string, content: string) => void
  onApprovalRequired?: (approval: ApprovalRequest) => void
  onDone?: (threadId: string, tripId?: string) => void
  onError?: (message: string) => void
}

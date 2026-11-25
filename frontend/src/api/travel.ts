// ═══════════════════════════════════════════════════════
// Travel API Client — SSE streaming + REST helpers
// ═══════════════════════════════════════════════════════

import type { SSECallbacks, ApprovalRequest, TripRecord } from '../types/travel'
import { useAuthStore } from '../stores/auth'

const API_BASE = '/api/v1'

export async function travelFetch(url: string, init?: RequestInit): Promise<Response> {
  const auth = useAuthStore()
  const token = auth.token
  const sessionVersion = auth.sessionVersion
  const headers = new Headers(init?.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(url, { ...init, headers })
  if (token && response.status === 401 && auth.sessionVersion === sessionVersion) auth.logout()
  return response
}

// ── Clarification ─────────────────────────────────────

export interface ClarifyResponse {
  action: 'ask' | 'ready'
  message: string
  travel_request: Record<string, any>
  missing_fields: string[]
  turn: number
  thread_id: string
}

export interface ClarifyInput {
  query: string
  history?: { role: string; content: string }[]
  travel_request?: Record<string, any> | null
  thread_id?: string
}

export async function clarifyRequest(input: ClarifyInput, signal?: AbortSignal): Promise<ClarifyResponse> {
  const res = await travelFetch(`${API_BASE}/chat/clarify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
    signal,
  })
  if (!res.ok) {
    throw new Error(`Clarify failed: ${res.status}`)
  }
  return res.json()
}

// ── SSE Streaming ─────────────────────────────────────

export function streamTravelPlanning(
  query: string,
  callbacks: SSECallbacks,
  threadId?: string,
): AbortController {
  const controller = new AbortController()

  travelFetch(`${API_BASE}/trips/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query,
      thread_id: threadId || crypto.randomUUID(),
    }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        callbacks.onError?.(`HTTP ${response.status}: ${response.statusText}`)
        return
      }

      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let currentEvent = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              _dispatch(currentEvent, data, callbacks)
            } catch {
              // skip malformed JSON
            }
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        callbacks.onError?.(err.message)
      }
    })

  return controller
}

function _dispatch(event: string, data: any, cb: SSECallbacks): void {
  switch (event) {
    case 'agent_start':
      cb.onAgentStart?.(data.agent, data.display, data.progress)
      break
    case 'agent_done':
      cb.onAgentDone?.(data.agent, data.summary, data.progress, data.data)
      break
    case 'token':
      cb.onToken?.(data.agent, data.content)
      break
    case 'approval_required':
      cb.onApprovalRequired?.(data as ApprovalRequest)
      break
    case 'done':
      cb.onDone?.(data.thread_id, data.trip_id)
      break
    case 'error':
      cb.onError?.(data.message)
      break
  }
}

export async function getTrip(tripId: string, signal?: AbortSignal): Promise<TripRecord> {
  const res = await travelFetch(`${API_BASE}/trips/${tripId}`, { signal })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function decideTrip(
  tripId: string, action: 'approve' | 'adjust', version: number, feedback?: string,
): Promise<TripRecord> {
  const response = await travelFetch(`${API_BASE}/trips/${tripId}/decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, version, feedback }),
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(typeof error.detail === 'string' ? error.detail : `HTTP ${response.status}`)
  }
  return response.json()
}

export async function listTrips(): Promise<any[]> {
  const res = await travelFetch(`${API_BASE}/trips`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const data = await res.json()
  return data.trips || []
}

export async function getTripVersions(tripId: string): Promise<any[]> {
  const res = await travelFetch(`${API_BASE}/trips/${tripId}/versions`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const data = await res.json()
  return data.versions || []
}

export async function updateTrip(tripId: string, itinerary: Record<string, any>) {
  const res = await travelFetch(`${API_BASE}/trips/${tripId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ itinerary }),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function getProfile(): Promise<any> {
  const res = await travelFetch(`${API_BASE}/profile`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

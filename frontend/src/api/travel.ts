// ═══════════════════════════════════════════════════════
// Travel API Client — SSE streaming + REST helpers
// ═══════════════════════════════════════════════════════

import type { SSECallbacks, ApprovalRequest } from '../types/travel'

const API_BASE = '/api/v1'

function _getToken(): string | null {
  return localStorage.getItem('travel_auth_token')
}

function _getUserId(): string {
  try {
    const user = JSON.parse(localStorage.getItem('travel_auth_user') || 'null')
    return user?.user_id || 'anonymous'
  } catch {
    return 'anonymous'
  }
}

function _authHeaders(): Record<string, string> {
  const token = _getToken()
  if (token) return { Authorization: `Bearer ${token}` }
  return {}
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

export async function clarifyRequest(input: ClarifyInput): Promise<ClarifyResponse> {
  const res = await fetch(`${API_BASE}/chat/clarify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ..._authHeaders() },
    body: JSON.stringify(input),
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

  fetch(`${API_BASE}/trips/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ..._authHeaders() },
    body: JSON.stringify({
      query,
      thread_id: threadId || crypto.randomUUID(),
      user_id: _getUserId(),
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

export function streamResumePlanning(
  threadId: string,
  action: string,
  feedback: string,
  edits: Record<string, any> | null,
  callbacks: SSECallbacks,
): AbortController {
  const controller = new AbortController()

  fetch(`${API_BASE}/trips/resume`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ..._authHeaders() },
    body: JSON.stringify({
      thread_id: threadId,
      action,
      feedback: feedback || '',
      edits: edits || null,
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

export async function getTrip(tripId: string) {
  const res = await fetch(`${API_BASE}/trips/${tripId}`, {
    headers: _authHeaders(),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function listTrips(): Promise<any[]> {
  const res = await fetch(`${API_BASE}/trips?user_id=${_getUserId()}`, {
    headers: _authHeaders(),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const data = await res.json()
  return data.trips || []
}

export async function getTripVersions(tripId: string): Promise<any[]> {
  const res = await fetch(`${API_BASE}/trips/${tripId}/versions`, {
    headers: _authHeaders(),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const data = await res.json()
  return data.versions || []
}

export async function updateTrip(tripId: string, itinerary: Record<string, any>) {
  const res = await fetch(`${API_BASE}/trips/${tripId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ..._authHeaders() },
    body: JSON.stringify({ itinerary }),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function getProfile(): Promise<any> {
  const res = await fetch(`${API_BASE}/profile?user_id=${_getUserId()}`, {
    headers: _authHeaders(),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

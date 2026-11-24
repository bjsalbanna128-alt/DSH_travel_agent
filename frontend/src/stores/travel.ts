import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  Itinerary, DayPlan, ApprovalRequest, ChatMessage,
  VersionInfo, ProgressInfo,
} from '../types/travel'
import { streamTravelPlanning, clarifyRequest, travelFetch } from '../api/travel'
import type { ClarifyResponse } from '../api/travel'

export const useTravelStore = defineStore('travel', () => {
  // ── State ──────────────────────────────────────────
  const threadId = ref<string | null>(null)
  const currentTripId = ref<string | null>(null)
  const userQuery = ref('')

  const progress = ref<ProgressInfo>({
    overall_percent: 0,
    current_phase: '',
    agents: [],
    is_streaming: false,
  })

  const itinerary = ref<Itinerary | null>(null)
  const dayPlans = ref<DayPlan[]>([])
  const pendingApproval = ref<ApprovalRequest | null>(null)
  const messages = ref<ChatMessage[]>([])
  const versions = ref<VersionInfo[]>([])
  const currentVersion = ref(1)
  const errors = ref<string[]>([])
  const abortController = ref<AbortController | null>(null)

  // ── Clarification state ──
  const clarifyMessages = ref<{ role: string; content: string }[]>([])
  const clarifyTravelRequest = ref<Record<string, any> | null>(null)
  const clarifyThreadId = ref<string | null>(null)
  const isClarifying = ref(false)
  const isReady = ref(false)

  // ── Computed ───────────────────────────────────────
  const isStreaming = computed(() => progress.value.is_streaming)
  const totalDays = computed(() => itinerary.value?.duration_days ?? 0)

  // ── Actions ────────────────────────────────────────
  function addMessage(role: ChatMessage['role'], content: string) {
    messages.value.push({
      id: crypto.randomUUID(),
      role,
      content,
      timestamp: new Date().toISOString(),
    })
  }

  // ── Clarification action ────────────────────────────
  let clarificationController: AbortController | undefined

  async function sendClarifyMessage(query: string) {
    clarificationController?.abort()
    const controller = new AbortController()
    clarificationController = controller
    isClarifying.value = true
    clarifyMessages.value.push({ role: 'user', content: query })

    try {
      const result: ClarifyResponse = await clarifyRequest({
        query,
        history: clarifyMessages.value.slice(0, -1), // exclude the just-added message
        travel_request: clarifyTravelRequest.value,
        thread_id: clarifyThreadId.value ?? undefined,
      }, controller.signal)
      if (controller.signal.aborted) return null

      clarifyMessages.value.push({ role: 'agent', content: result.message })
      clarifyTravelRequest.value = result.travel_request
      clarifyThreadId.value = result.thread_id

      if (result.action === 'ready') {
        isReady.value = true
        isClarifying.value = false
      } else {
        isClarifying.value = false
      }

      return result
    } catch (e: any) {
      if (controller.signal.aborted) return null
      isClarifying.value = false
      clarifyMessages.value.push({ role: 'agent', content: `抱歉，出错了：${e.message}` })
      return null
    }
  }

  function startPlanningWithClarifiedRequest() {
    if (!clarifyTravelRequest.value) return

    const query = clarifyMessages.value[0]?.content || ''
    userQuery.value = query
    threadId.value = crypto.randomUUID()
    currentTripId.value = null
    pendingApproval.value = null
    errors.value = []

    progress.value = {
      overall_percent: 0,
      current_phase: '',
      agents: [],
      is_streaming: true,
    }
    itinerary.value = null
    dayPlans.value = []

    addMessage('user', query)

    // Pass pre-filled travel_request to skip parse_request
    const ctrl = streamTravelPlanningWithPrefill(
      query,
      clarifyTravelRequest.value,
      threadId.value,
    )

    abortController.value = ctrl
  }

  // Wrapper that passes travel_request in the POST body
  function streamTravelPlanningWithPrefill(
    query: string,
    travelRequest: Record<string, any>,
    tid?: string,
  ): AbortController {
    const controller = new AbortController()

    travelFetch('/api/v1/trips/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query,
        thread_id: tid || crypto.randomUUID(),
        travel_request: travelRequest,
      }),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          progress.value.is_streaming = false
          errors.value.push(`HTTP ${response.status}`)
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
                dispatchPrefillEvent(currentEvent, data)
              } catch { /* skip */ }
            }
          }
        }
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          progress.value.is_streaming = false
          errors.value.push(err.message)
        }
      })

    return controller
  }

  function dispatchPrefillEvent(event: string, data: any) {
    switch (event) {
      case 'agent_start':
        if (data.agent === 'supervisor') break
        progress.value.current_phase = data.display
        progress.value.overall_percent = data.progress
        progress.value.agents.push({
          agent_name: data.agent,
          status: 'running',
          message: `${data.display}中...`,
        })
        break
      case 'agent_done': {
        if (data.agent === 'supervisor') break
        progress.value.overall_percent = data.progress
        const ag = progress.value.agents.find(a => a.agent_name === data.agent)
        if (ag) { ag.status = 'done'; ag.message = data.summary }
        if (data.data?.itinerary) {
          itinerary.value = data.data.itinerary
          dayPlans.value = data.data.itinerary.day_plans || []
        }
        break
      }
      case 'approval_required':
        receiveDraft(data)
        break
      case 'done':
        progress.value.is_streaming = false
        threadId.value = data.thread_id
        currentTripId.value = data.trip_id || data.thread_id
        addMessage('system', '行程规划完成')
        break
      case 'error':
        progress.value.is_streaming = false
        errors.value.push(data.message)
        addMessage('system', `出错：${data.message}`)
        break
    }
  }

  function continueClarify() {
    // Allow user to add more info after ready
    isReady.value = false
    isClarifying.value = false
  }

  function resetClarify() {
    clarificationController?.abort()
    clarificationController = undefined
    clarifyMessages.value = []
    clarifyTravelRequest.value = null
    clarifyThreadId.value = null
    isClarifying.value = false
    isReady.value = false
  }

  function startPlanning(query: string) {
    if (progress.value.is_streaming) return

    // Reset state
    userQuery.value = query
    progress.value = {
      overall_percent: 0,
      current_phase: '',
      agents: [],
      is_streaming: true,
    }
    itinerary.value = null
    dayPlans.value = []
    pendingApproval.value = null
    errors.value = []

    addMessage('user', query)

    const ctrl = streamTravelPlanning(query, {
      onAgentStart(agent, display, pct) {
        if (agent === 'supervisor') return
        progress.value.current_phase = display
        progress.value.overall_percent = pct
        progress.value.agents.push({
          agent_name: agent,
          status: 'running',
          message: `${display}中...`,
        })
      },

      onAgentDone(agent, summary, pct, data) {
        if (agent === 'supervisor') return
        progress.value.overall_percent = pct
        const ag = progress.value.agents.find(a => a.agent_name === agent)
        if (ag) {
          ag.status = 'done'
          ag.message = summary
        }
        // Live-update day_plans when compiler finishes
        if (data?.itinerary) {
          itinerary.value = data.itinerary
          dayPlans.value = data.itinerary.day_plans || []
        }
      },

      onToken(_agent, content) {
        // Token streaming — append to a live message
        const last = messages.value[messages.value.length - 1]
        if (last && last.role === 'agent' && !last.content.endsWith('...')) {
          last.content += content
        }
      },

      onApprovalRequired(approval) {
        receiveDraft(approval)
      },

      onDone(tid, tripId) {
        progress.value.is_streaming = false
        threadId.value = tid
        currentTripId.value = tripId || tid
        addMessage('system', '行程规划完成')
      },

      onError(msg) {
        progress.value.is_streaming = false
        errors.value.push(msg)
        addMessage('system', `出错：${msg}`)
      },
    }, crypto.randomUUID())

    abortController.value = ctrl
  }

  function cancelPlanning() {
    abortController.value?.abort()
    progress.value.is_streaming = false
  }

  function receiveDraft(approval: ApprovalRequest) {
    pendingApproval.value = approval
    threadId.value = approval.thread_id
    currentTripId.value = approval.trip_id
    itinerary.value = approval.data
    dayPlans.value = approval.data.day_plans || []
    progress.value.is_streaming = false
  }

  async function rollback(version: number) {
    currentVersion.value = version
  }

  function reset() {
    threadId.value = null
    currentTripId.value = null
    userQuery.value = ''
    progress.value = {
      overall_percent: 0,
      current_phase: '',
      agents: [],
      is_streaming: false,
    }
    itinerary.value = null
    dayPlans.value = []
    pendingApproval.value = null
    messages.value = []
    versions.value = []
    errors.value = []
  }

  return {
    threadId, currentTripId, userQuery,
    progress, itinerary, dayPlans, pendingApproval,
    messages, versions, currentVersion, errors,
    isStreaming, totalDays,
    clarifyMessages, clarifyTravelRequest, clarifyThreadId, isClarifying, isReady,
    sendClarifyMessage, startPlanningWithClarifiedRequest, continueClarify,
    startPlanning, cancelPlanning, rollback, reset, resetClarify, addMessage,
  }
})

<script setup lang="ts">
import { ref, nextTick, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()

const threadId = ref(crypto.randomUUID())
const ws = ref<WebSocket | null>(null)
const connected = ref(false)
const input = ref('')
const streaming = ref(false)
const currentTripId = ref('')
const travelRequest = ref<Record<string, any> | null>(null)
const clarificationHistory: { role: 'user' | 'assistant'; content: string }[] = []
const clarifying = ref(false)
const readyToPlan = ref(false)

interface ChatMessage {
  id: string
  role: 'user' | 'agent' | 'system'
  type: 'text' | 'progress' | 'clarify' | 'approval' | 'done' | 'error'
  content: string
  display?: string
  summary?: string
  progress?: number
  finished?: boolean
  data?: any
  timestamp: number
}

const messages = ref<ChatMessage[]>([])
const chatContainer = ref<HTMLElement | null>(null)

const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
const wsUrl = `${wsProtocol}//${window.location.host}/ws/chat/${threadId.value}`

function connect() {
  const token = auth.token
  if (!token) return
  const socket = new WebSocket(wsUrl)
  ws.value = socket

  socket.onopen = () => {
    socket.send(JSON.stringify({ type: 'auth', token }))
  }

  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      handleMessage(data)
    } catch {
      // skip malformed
    }
  }

  socket.onclose = (event) => {
    connected.value = false
    streaming.value = false
    clarifying.value = false
    if (event.code === 1008 && auth.token === token) {
      auth.logout()
      return
    }
    addSystem('连接已断开')
  }

  socket.onerror = () => {
    connected.value = false
    clarifying.value = false
    addSystem('连接失败，请刷新页面重试', 'error')
  }
}

function handleMessage(data: any) {
  const type = data.type || ''

  switch (type) {
    case 'authenticated':
      connected.value = true
      addSystem('已连接到 AI 旅行规划助手')
      break
    case 'agent_start':
      messages.value.push({
        id: `agent-${data.agent}-${Date.now()}`,
        role: 'agent',
        type: 'progress',
        content: '',
        display: data.display || data.agent,
        progress: data.progress || 0,
        finished: false,
        timestamp: Date.now(),
      })
      streaming.value = true
      break

    case 'agent_done': {
      // Update or add progress card
      const existing = messages.value.find(
        m => m.type === 'progress' && m.display === data.display && !m.finished
      )
      if (existing) {
        existing.finished = true
        existing.summary = data.summary || ''
        existing.progress = data.progress || 1
        if (data.data) existing.data = data.data
      } else {
        messages.value.push({
          id: `agent-done-${data.agent}-${Date.now()}`,
          role: 'agent',
          type: 'progress',
          content: '',
          display: data.display || data.agent,
          summary: data.summary || '',
          progress: data.progress || 1,
          finished: true,
          data: data.data,
          timestamp: Date.now(),
        })
      }
      break
    }

    case 'clarify': {
      clarifying.value = false
      travelRequest.value = data.travel_request || travelRequest.value
      readyToPlan.value = data.action === 'ready'
      const reply = data.message || (readyToPlan.value ? '已收齐需求，可以开始规划。' : '请提供更多信息。')
      clarificationHistory.push({ role: 'assistant', content: reply })
      addAgent(reply)
      break
    }

    case 'approval_required':
      messages.value.push({
        id: `approval-${Date.now()}`,
        role: 'system',
        type: 'approval',
        content: '草稿已生成，待确认',
        data: data.data,
        timestamp: Date.now(),
      })
      streaming.value = false
      break

    case 'done':
      currentTripId.value = data.trip_id || ''
      streaming.value = false
      addSystem(
        '规划完成！' + (data.trip_id ? ` [查看详情](/trip/${data.trip_id})` : '')
      )
      if (data.trip_id) {
        messages.value.push({
          id: `done-${Date.now()}`,
          role: 'system',
          type: 'done',
          content: '行程规划完成',
          data: { trip_id: data.trip_id },
          timestamp: Date.now(),
        })
      }
      break

    case 'error':
      addSystem(data.message || '发生错误', 'error')
      streaming.value = false
      clarifying.value = false
      break

    case 'cancelled':
      addSystem('规划已取消')
      streaming.value = false
      break
  }

  scrollToBottom()
}

function addSystem(text: string, msgType: 'text' | 'error' = 'text') {
  messages.value.push({
    id: `sys-${Date.now()}`,
    role: 'system',
    type: msgType === 'error' ? 'error' : 'text',
    content: text,
    timestamp: Date.now(),
  })
}

function addAgent(text: string) {
  messages.value.push({
    id: `agent-msg-${Date.now()}`,
    role: 'agent',
    type: 'text',
    content: text,
    timestamp: Date.now(),
  })
}

function scrollToBottom() {
  nextTick(() => {
    const el = chatContainer.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

function send() {
  const text = input.value.trim()
  if (!text || !ws.value || !connected.value || clarifying.value || streaming.value) return

  // Add user message
  messages.value.push({
    id: `user-${Date.now()}`,
    role: 'user',
    type: 'text',
    content: text,
    timestamp: Date.now(),
  })

  ws.value.send(JSON.stringify({
    type: 'chat',
    query: text,
    history: clarificationHistory,
    travel_request: travelRequest.value,
  }))
  clarificationHistory.push({ role: 'user', content: text })
  clarifying.value = true

  input.value = ''
  scrollToBottom()
}

function startPlanning() {
  if (!ws.value || !connected.value || !readyToPlan.value || !travelRequest.value
    || clarifying.value || streaming.value) return
  const query = clarificationHistory.filter(turn => turn.role === 'user').map(turn => turn.content).join('。')
  ws.value.send(JSON.stringify({ type: 'start', query, travel_request: travelRequest.value }))
  readyToPlan.value = false
  streaming.value = true
}

function goToTrip(id: string) {
  router.push(`/trip/${id}`)
}

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

onMounted(() => {
  connect()
  addSystem('输入您的旅行需求，例如："带爸妈去成都5天"')
})

onUnmounted(() => {
  ws.value?.close()
})
</script>

<template>
  <div class="chat-page">
    <!-- Header -->
    <div class="chat-header">
      <el-button text @click="router.push('/')">← 首页</el-button>
      <div class="header-center">
        <h2>AI 旅行规划</h2>
        <span :class="['status-dot', connected ? 'connected' : 'disconnected']" />
        <span class="status-text">{{ connected ? '在线' : '离线' }}</span>
      </div>
      <div class="header-right" />
    </div>

    <!-- Messages -->
    <div ref="chatContainer" class="chat-messages">
      <!-- Welcome -->
      <div v-if="messages.length === 0" class="welcome">
        <div class="welcome-icon">🌍</div>
        <h3>智能旅行规划助手</h3>
        <p>告诉我你的旅行计划，多个 AI Agent 将协作完成规划</p>
        <div class="examples">
          <span
            v-for="ex in ['带爸妈去成都5天', '北京3日文化之旅', '上海周末亲子游', '西安4天历史探索']"
            :key="ex"
            class="example-tag"
            @click="input = ex; send()"
          >{{ ex }}</span>
        </div>
      </div>

      <!-- Message list -->
      <div v-for="msg in messages" :key="msg.id" class="msg-wrapper">
        <!-- User message -->
        <div v-if="msg.role === 'user'" class="msg-row msg-row-user">
          <div class="msg-bubble msg-bubble-user">{{ msg.content }}</div>
          <span class="msg-time">{{ formatTime(msg.timestamp) }}</span>
        </div>

        <!-- Agent progress card -->
        <div v-else-if="msg.type === 'progress'" class="msg-row msg-row-agent">
          <div class="progress-card" :class="{ 'progress-done': msg.finished }">
            <div class="progress-header">
              <el-icon v-if="!msg.finished" class="is-loading progress-spin" :size="16">
                <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="3" stroke-dasharray="31.4 31.4" stroke-linecap="round"/></svg>
              </el-icon>
              <el-icon v-else color="#67c23a" :size="16">
                <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2"/><path d="M8 12l3 3 5-5" fill="none" stroke="currentColor" stroke-width="2"/></svg>
              </el-icon>
              <span class="progress-name">{{ msg.display }}</span>
              <span v-if="msg.finished && msg.summary" class="progress-summary">{{ msg.summary }}</span>
            </div>
            <el-progress
              v-if="!msg.finished"
              :percentage="Math.round((msg.progress || 0) * 100)"
              :show-text="false"
              :stroke-width="3"
              style="margin-top: 6px"
            />
          </div>
        </div>

        <!-- Approval card -->
        <div v-else-if="msg.type === 'approval'" class="msg-row msg-row-system">
          <div class="approval-card">
            <div class="approval-icon">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#e6a23c" stroke-width="2">
                <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><circle cx="12" cy="16" r="1" fill="#e6a23c"/>
              </svg>
            </div>
            <div class="approval-body">
              <p class="approval-question">{{ msg.content }}</p>
              <el-button type="primary" size="small" @click="goToTrip(msg.data.trip_id)">
                查看待确认草稿
              </el-button>
            </div>
          </div>
        </div>

        <!-- Done card -->
        <div v-else-if="msg.type === 'done'" class="msg-row msg-row-system">
          <div class="done-card">
            <div class="done-icon">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="#67c23a" stroke-width="2">
                <circle cx="12" cy="12" r="10"/><path d="M8 12l3 3 5-5"/>
              </svg>
            </div>
            <span>{{ msg.content }}</span>
            <el-button
              v-if="msg.data?.trip_id"
              type="primary"
              size="small"
              style="margin-left: 10px"
              @click="goToTrip(msg.data.trip_id)"
            >
              查看行程 →
            </el-button>
          </div>
        </div>

        <!-- Agent text message -->
        <div v-else-if="msg.role === 'agent' && msg.type === 'text'" class="msg-row msg-row-agent">
          <div class="msg-bubble msg-bubble-agent">{{ msg.content }}</div>
          <span class="msg-time">{{ formatTime(msg.timestamp) }}</span>
        </div>

        <!-- System message -->
        <div v-else class="msg-system-line">
          <span :class="msg.type === 'error' ? 'system-error' : ''">{{ msg.content }}</span>
        </div>
      </div>

      <!-- Streaming indicator -->
      <div v-if="streaming" class="streaming-indicator">
        <span class="dot-pulse" />
        <span>AI 正在规划...</span>
      </div>
    </div>

    <!-- Input -->
    <div class="chat-input-bar">
      <div class="inspiration-entry">
        <span>没有想法？</span>
        <el-button text type="primary" size="small" @click="router.push('/inspiration')">
          试试随机旅行
        </el-button>
      </div>
      <el-button
        v-if="readyToPlan"
        type="primary"
        :disabled="!connected || clarifying || streaming"
        @click="startPlanning"
      >
        开始规划
      </el-button>
      <el-input
        v-model="input"
        placeholder="输入旅行需求..."
        size="large"
        :disabled="!connected || streaming || clarifying"
        @keydown.enter.exact="send"
      >
        <template #append>
          <el-button
            type="primary"
            :disabled="!connected || !input.trim() || streaming || clarifying"
            :loading="clarifying"
            @click="send"
          >
            发送
          </el-button>
        </template>
      </el-input>
    </div>
  </div>
</template>

<style scoped>
.chat-page {
  display: flex; flex-direction: column; height: calc(100vh - 1px);
  max-width: 800px; margin: 0 auto;
}

/* Header */
.chat-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 16px; background: #fff; border-bottom: 1px solid #ebeef5;
  flex-shrink: 0;
}
.header-center { display: flex; align-items: center; gap: 8px; }
.header-center h2 { font-size: 17px; margin: 0; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; }
.connected { background: #67c23a; }
.disconnected { background: #f56c6c; }
.status-text { font-size: 12px; color: #909399; }
.header-right { width: 80px; }

/* Messages area */
.chat-messages {
  flex: 1; overflow-y: auto; padding: 16px 20px;
  background: #f5f7fa;
}

/* Welcome */
.welcome { text-align: center; padding: 48px 20px; }
.welcome-icon { font-size: 48px; margin-bottom: 16px; }
.welcome h3 { font-size: 20px; margin: 0 0 8px; color: #303133; }
.welcome p { font-size: 14px; color: #909399; margin: 0 0 20px; }
.examples { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }
.example-tag {
  font-size: 13px; color: #409eff; background: #ecf5ff;
  padding: 6px 14px; border-radius: 16px; cursor: pointer;
  transition: background .2s;
}
.example-tag:hover { background: #d9ecff; }

/* Message rows */
.msg-wrapper { margin-bottom: 10px; }
.msg-row { display: flex; align-items: flex-end; gap: 8px; margin-bottom: 4px; }
.msg-row-user { flex-direction: row-reverse; }
.msg-row-agent { flex-direction: row; }
.msg-row-system { justify-content: center; }
.msg-time { font-size: 11px; color: #c0c4cc; flex-shrink: 0; }

/* Bubbles */
.msg-bubble {
  max-width: 70%; padding: 10px 14px; border-radius: 14px;
  font-size: 14px; line-height: 1.5; word-break: break-word;
}
.msg-bubble-user {
  background: #409eff; color: #fff;
  border-bottom-right-radius: 4px;
}
.msg-bubble-agent {
  background: #fff; color: #303133; box-shadow: 0 1px 3px rgba(0,0,0,.06);
  border-bottom-left-radius: 4px;
}

/* Progress card */
.progress-card {
  background: #fff; border-radius: 10px; padding: 10px 14px;
  box-shadow: 0 1px 3px rgba(0,0,0,.06); min-width: 240px;
}
.progress-done { opacity: 0.7; }
.progress-header { display: flex; align-items: center; gap: 6px; }
.progress-spin { color: #409eff; }
.progress-name { font-size: 13px; font-weight: 500; color: #303133; }
.progress-summary { font-size: 12px; color: #67c23a; margin-left: auto; }

/* Approval card */
.approval-card {
  display: flex; align-items: center; gap: 10px;
  background: #fffbe6; border: 1px solid #f5dab1; border-radius: 10px;
  padding: 14px 16px; max-width: 90%;
}
.approval-icon { flex-shrink: 0; }
.approval-body { flex: 1; }
.approval-question { font-size: 14px; font-weight: 500; color: #303133; margin: 0 0 6px; }
.approval-options { display: flex; gap: 6px; flex-wrap: wrap; }
.approval-opt-tag {
  font-size: 12px; color: #e6a23c; background: #fef0c7;
  padding: 2px 8px; border-radius: 10px;
}

/* Done card */
.done-card {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  background: #f0f9eb; border-radius: 8px; padding: 10px 16px;
  font-size: 14px; color: #67c23a;
}
.done-icon { flex-shrink: 0; }

/* System line */
.msg-system-line {
  text-align: center; font-size: 12px; color: #909399;
  padding: 8px 0;
}
.system-error { color: #f56c6c; }

/* Streaming */
.streaming-indicator {
  display: flex; align-items: center; gap: 8px; padding: 8px 0;
  font-size: 13px; color: #909399;
}
.dot-pulse {
  width: 8px; height: 8px; background: #409eff; border-radius: 50%;
  animation: pulse 1.2s infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: .4; transform: scale(.8); }
}

/* Input bar */
.chat-input-bar { padding: 12px 16px; background: #fff; border-top: 1px solid #ebeef5; flex-shrink: 0; }

/* Random template entry, always visible above the input */
.inspiration-entry {
  display: flex; align-items: center; justify-content: center; gap: 2px;
  font-size: 13px; color: #909399; margin-bottom: 8px;
}
</style>


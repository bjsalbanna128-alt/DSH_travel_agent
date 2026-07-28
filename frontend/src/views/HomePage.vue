<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useTravelStore } from '../stores/travel'

const store = useTravelStore()
const router = useRouter()

const inputText = ref('')
const chatContainer = ref<HTMLElement | null>(null)
const sending = ref(false)

const exampleQueries = [
  '和兄弟去成都玩3天',
  '带爸妈去三亚5天，预算1.5万',
  '一个人去大理躺4天',
  '和闺蜜去上海4天，想逛街吃美食',
]

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || sending.value) return
  inputText.value = ''
  sending.value = true

  await store.sendClarifyMessage(text)
  sending.value = false

  await nextTick()
  scrollToBottom()
}

function confirmAndStart() {
  store.startPlanningWithClarifiedRequest()
  router.push('/plan')
}

function useExample(query: string) {
  inputText.value = query
  sendMessage()
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

function scrollToBottom() {
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}

watch(() => store.clarifyMessages.length, () => {
  nextTick(() => scrollToBottom())
})

// Reset clarify state when entering this page
store.resetClarify()
</script>

<template>
  <div class="home-page">
    <!-- Header -->
    <div class="home-header">
      <h1>AI 旅行规划师</h1>
      <p>告诉我你想去哪，剩下的交给我</p>
      <div class="header-links">
        <el-button type="primary" @click="router.push('/chat')">聊天规划 (WebSocket)</el-button>
        <el-button text @click="router.push('/history')">历史行程</el-button>
      </div>
    </div>

    <!-- Chat area -->
    <div class="chat-wrapper">
      <div ref="chatContainer" class="chat-messages">
        <!-- Empty state -->
        <div v-if="store.clarifyMessages.length === 0" class="chat-empty">
          <div class="empty-icon">✈️</div>
          <p>试着告诉我你的旅行计划吧</p>
          <div class="example-chips">
            <el-tag
              v-for="q in exampleQueries"
              :key="q"
              class="example-chip"
              @click="useExample(q)"
            >
              {{ q }}
            </el-tag>
          </div>
        </div>

        <!-- Messages -->
        <div
          v-for="(msg, i) in store.clarifyMessages"
          :key="i"
          :class="['chat-bubble', msg.role === 'user' ? 'bubble-user' : 'bubble-agent']"
        >
          <div class="bubble-avatar">
            {{ msg.role === 'user' ? '👤' : '🤖' }}
          </div>
          <div class="bubble-content">
            <div class="bubble-text">{{ msg.content }}</div>
          </div>
        </div>

        <!-- Thinking indicator -->
        <div v-if="sending" class="chat-bubble bubble-agent">
          <div class="bubble-avatar">🤖</div>
          <div class="bubble-content">
            <div class="thinking-dots">
              <span /><span /><span />
            </div>
          </div>
        </div>
      </div>

      <!-- Input area -->
      <div class="chat-input-area">
        <el-input
          v-model="inputText"
          type="textarea"
          :rows="1"
          placeholder="说说你的旅行计划..."
          :disabled="sending || store.isReady"
          @keydown="handleKeydown"
        />
        <el-button
          type="primary"
          :disabled="!inputText.trim() || sending"
          :loading="sending"
          @click="sendMessage"
        >
          发送
        </el-button>
      </div>

      <!-- Ready confirmation card -->
      <div v-if="store.isReady" class="confirm-card">
        <div class="confirm-check">✓ 信息已就绪</div>
        <div class="confirm-detail">
          <div class="confirm-row">
            <span class="confirm-label">目的地</span>
            <span class="confirm-value">{{ store.clarifyTravelRequest?.destination || '—' }}</span>
          </div>
          <div class="confirm-row">
            <span class="confirm-label">天数</span>
            <span class="confirm-value">{{ store.clarifyTravelRequest?.days || '—' }} 天</span>
          </div>
          <div class="confirm-row">
            <span class="confirm-label">人数</span>
            <span class="confirm-value">
              {{ (store.clarifyTravelRequest?.adults || 0) + (store.clarifyTravelRequest?.children || 0) + (store.clarifyTravelRequest?.elderly || 0) || '—' }} 人
            </span>
          </div>
          <div class="confirm-row">
            <span class="confirm-label">预算</span>
            <span class="confirm-value">{{ store.clarifyTravelRequest?.budget_total ? '¥' + store.clarifyTravelRequest.budget_total.toLocaleString() : '不限' }}</span>
          </div>
          <div class="confirm-row">
            <span class="confirm-label">偏好</span>
            <span class="confirm-value">{{ (store.clarifyTravelRequest?.preferences || []).join('、') || '综合体验' }}</span>
          </div>
        </div>
        <div class="confirm-actions">
          <el-button type="primary" size="large" @click="confirmAndStart">
            开始规划行程
          </el-button>
          <el-button text @click="store.continueClarify()">
            补充信息
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.home-page {
  max-width: 680px;
  margin: 0 auto;
  padding: 24px 16px;
  height: calc(100vh - 60px);
  display: flex;
  flex-direction: column;
}

.home-header {
  text-align: center;
  margin-bottom: 20px;
}
.home-header h1 {
  font-size: 28px;
  color: #303133;
  margin: 0 0 6px;
}
.home-header p {
  font-size: 14px;
  color: #909399;
  margin: 0;
}
.header-links {
  margin-top: 14px;
  display: flex;
  gap: 8px;
  justify-content: center;
}

/* Chat wrapper */
.chat-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0,0,0,.06);
  overflow: hidden;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

/* Empty state */
.chat-empty {
  text-align: center;
  padding: 40px 0;
}
.empty-icon { font-size: 48px; margin-bottom: 12px; }
.chat-empty p { color: #909399; margin-bottom: 16px; }
.example-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}
.example-chip {
  cursor: pointer;
  padding: 6px 14px !important;
  font-size: 13px;
}
.example-chip:hover {
  background: #ecf5ff;
  color: #409eff;
}

/* Bubbles */
.chat-bubble {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  animation: fadeIn .3s ease;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
.bubble-user { flex-direction: row-reverse; }
.bubble-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #f0f2f5;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}
.bubble-content { max-width: 75%; }
.bubble-text {
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
}
.bubble-user .bubble-text {
  background: #409eff;
  color: #fff;
  border-bottom-right-radius: 4px;
}
.bubble-agent .bubble-text {
  background: #f0f2f5;
  color: #303133;
  border-bottom-left-radius: 4px;
}

/* Thinking dots */
.thinking-dots {
  display: flex;
  gap: 4px;
  padding: 8px 14px;
}
.thinking-dots span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #c0c4cc;
  animation: bounce 1.4s infinite both;
}
.thinking-dots span:nth-child(2) { animation-delay: .2s; }
.thinking-dots span:nth-child(3) { animation-delay: .4s; }
@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

/* Input */
.chat-input-area {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid #ebeef5;
  align-items: flex-end;
}
.chat-input-area :deep(.el-textarea__inner) {
  resize: none;
}

.confirm-card {
  padding: 20px;
  border-top: 1px solid #ebeef5;
  background: #f0f9eb;
}
.confirm-check {
  font-size: 16px;
  font-weight: 600;
  color: #67c23a;
  margin-bottom: 14px;
}
.confirm-detail {
  background: #fff;
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 14px;
}
.confirm-row {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  font-size: 14px;
}
.confirm-label {
  color: #909399;
}
.confirm-value {
  color: #303133;
  font-weight: 500;
}
.confirm-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: center;
}
</style>

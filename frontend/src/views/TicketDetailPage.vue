<script setup lang="ts">
import { computed, nextTick, onScopeDispose, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { adminError, AdminRequestError } from '../api/adminResources'
import { supportApi } from '../api/support'
import { useAdminQuery } from '../composables/useAdminQuery'
import { useAuthStore } from '../stores/auth'
import {
  categoryLabels, priorityLabels, supportTime, ticketStatusLabels,
  type AdminTicketDetail, type AdminTicketHandling, type TicketDetail, type TicketHandling, type TicketPriority,
} from '../types/support'

const props = defineProps<{ operator?: boolean }>()
const route = useRoute()
const auth = useAuthStore()
const ticketId = computed(() => String(route.params.id))
const { data, error, loading, load, clear } = useAdminQuery<TicketDetail | AdminTicketDetail>(signal => props.operator
  ? supportApi.adminTicket(ticketId.value, signal)
  : supportApi.myTicket(ticketId.value, signal))
const saved = ref<AdminTicketDetail>()
const item = computed(() => data.value ?? saved.value)
const staffTicket = computed(() => props.operator ? item.value as AdminTicketDetail | undefined : undefined)
const canEdit = computed(() => Boolean(staffTicket.value &&
  (staffTicket.value.status === 'new' || staffTicket.value.assignee?.id === auth.userId)))
const canClose = computed(() => canEdit.value && staffTicket.value?.status === 'processing')
const targetRound = computed(() => /^\d+$/.test(String(route.query.round)) ? Number(route.query.round) : null)
const priority = ref<TicketPriority>('normal')
const reply = ref('')
const actionError = ref('')
const busy = ref(false)
let mutation: AbortController | undefined

watch(ticketId, () => {
  mutation?.abort()
  busy.value = false
  saved.value = undefined
  reply.value = ''
  actionError.value = ''
  clear()
  void load()
}, { immediate: true })
watch(staffTicket, value => { if (value) priority.value = value.priority })
watch([item, targetRound], async ([value, round]) => {
  if (!round || !value?.handlings.some(row => row.round === round)) return
  await nextTick()
  const section = document.getElementById(`ticket-handling-${round}`)
  section?.scrollIntoView({ block: 'nearest' })
  section?.focus({ preventScroll: true })
})
onScopeDispose(() => mutation?.abort())

function operatorRecord(row: TicketHandling): AdminTicketHandling | undefined {
  return 'handler_id' in row ? row as AdminTicketHandling : undefined
}

async function mutate(action: 'claim' | 'reopen' | 'close' | 'priority') {
  const ticket = staffTicket.value
  if (!ticket || busy.value) return
  actionError.value = ''
  if (action === 'close' && !reply.value.trim()) {
    actionError.value = '请填写给游客的处理结果。'
    return
  }
  busy.value = true
  const request = new AbortController()
  mutation = request
  try {
    const result = action === 'priority'
      ? await supportApi.setPriority(ticket.id, ticket.revision, priority.value, request.signal)
      : await supportApi.ticketAction(ticket.id, action, ticket.revision, action === 'close' ? reply.value : undefined, request.signal)
    if (request.signal.aborted) return
    saved.value = result
    clear()
    if (action === 'close' || action === 'reopen') reply.value = ''
    ElMessage.success({ claim: '已接单', reopen: '已重新打开并接手', close: '已关闭本轮工单', priority: '已保存优先级' }[action])
  } catch (failure) {
    if (request.signal.aborted) return
    actionError.value = adminError(failure)
    if (failure instanceof AdminRequestError && [403, 409].includes(failure.status)) {
      await load()
    }
  } finally {
    if (mutation === request) busy.value = false
  }
}
</script>

<template>
  <section class="resource-page support-page">
    <header class="resource-titlebar support-title">
      <h1>工单详情</h1>
      <div class="resource-actions">
        <router-link class="resource-link" :to="{ name: operator ? 'admin-tickets' : 'my-tickets' }">返回工单列表</router-link>
        <el-button v-if="item" :loading="loading" :disabled="busy" @click="load">刷新</el-button>
      </div>
    </header>
    <el-alert v-if="error" :title="error" class="support-error" type="error" :closable="false" show-icon />
    <el-button v-if="error && !item" :loading="loading" @click="load">重试</el-button>
    <p v-if="loading && !item" role="status">正在加载工单…</p>
    <template v-if="item">
      <section class="resource-panel">
        <h2 class="support-section-title">{{ item.subject }}</h2>
        <div class="resource-actions">
          <el-tag>{{ ticketStatusLabels[item.status] }}</el-tag>
          <span class="resource-muted">{{ categoryLabels[item.category] }}</span>
        </div>
        <dl class="support-meta">
          <div><dt>工单号</dt><dd>{{ item.number }}</dd></div>
          <div><dt>提交时间</dt><dd>{{ supportTime(item.created_at) }}</dd></div>
          <div v-if="staffTicket"><dt>提交人</dt><dd>{{ staffTicket.submitter.username }}</dd></div>
          <div v-if="staffTicket"><dt>当前负责人</dt><dd>{{ staffTicket.assignee?.username ?? '待接单' }}</dd></div>
          <div v-if="staffTicket"><dt>优先级</dt><dd>{{ priorityLabels[staffTicket.priority] }}</dd></div>
        </dl>
        <p class="support-copy ticket-content">{{ item.content }}</p>
      </section>

      <section v-if="staffTicket" class="resource-panel">
        <h2 class="support-section-title">处理工单</h2>
        <el-alert v-if="actionError" class="support-error" :title="actionError" type="error" :closable="false" show-icon />
        <div class="resource-actions">
          <el-button v-if="item.status === 'new'" type="primary" :loading="busy" @click="mutate('claim')">开始处理</el-button>
          <el-button v-if="item.status === 'closed'" type="primary" :loading="busy" @click="mutate('reopen')">重新打开并处理</el-button>
          <p v-if="item.status === 'processing' && !canEdit">已由 {{ staffTicket.assignee?.username }} 处理</p>
          <template v-if="canEdit">
            <el-select v-model="priority" aria-label="调整优先级" class="ticket-priority" :disabled="busy">
              <el-option v-for="(label, value) in priorityLabels" :key="value" :value="value" :label="label" />
            </el-select>
            <el-button :disabled="busy || priority === staffTicket.priority" @click="mutate('priority')">保存优先级</el-button>
          </template>
        </div>
        <el-form v-if="canClose" class="ticket-reply" label-position="top" :disabled="busy" @submit.prevent="mutate('close')">
          <el-form-item label="给游客的处理结果" required>
            <el-input v-model="reply" type="textarea" :rows="4" :maxlength="4000" show-word-limit />
          </el-form-item>
          <el-button native-type="submit" type="primary" :loading="busy">提交结果并关闭</el-button>
        </el-form>
      </section>

      <section class="resource-panel">
        <h2 class="support-section-title">处理记录</h2>
        <p v-if="!item.handlings.length" class="resource-muted">等待运营接单</p>
        <ol v-else class="ticket-history">
          <li v-for="row in item.handlings" :id="`ticket-handling-${row.round}`" :key="row.round"
            :class="{ 'target-round': row.round === targetRound }" tabindex="-1">
            <h3>第 {{ row.round }} 轮 · {{ row.completed_at ? '已完成' : '处理中' }}</h3>
            <dl class="support-meta">
              <template v-if="operatorRecord(row)">
                <div><dt>处理人</dt><dd>{{ operatorRecord(row)?.handler_name }}（{{ operatorRecord(row)?.handler_id }}）</dd></div>
                <div><dt>接单时间</dt><dd>{{ supportTime(operatorRecord(row)?.claimed_at) }}</dd></div>
                <div v-if="row.completed_at"><dt>完成人 ID</dt><dd>{{ operatorRecord(row)?.completed_by }}</dd></div>
              </template>
              <div v-if="row.completed_at"><dt>完成时间</dt><dd>{{ supportTime(row.completed_at) }}</dd></div>
              <div v-if="row.completed_at"><dt>处理结果</dt><dd class="support-copy">{{ row.result }}</dd></div>
            </dl>
          </li>
        </ol>
      </section>
    </template>
  </section>
</template>

<style scoped>
.ticket-content, .ticket-reply { margin-top: 16px; }
.ticket-priority { width: 130px; }
.ticket-history { list-style: none; display: grid; gap: 12px; }
.ticket-history li { border: 1px solid #e0e8f2; border-radius: 7px; padding: 13px; }
.ticket-history .target-round { border-color: #4684ce; background: #f0f6ff; }
</style>

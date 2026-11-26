<script setup lang="ts">
import { computed, onMounted, onScopeDispose, reactive, ref, watch } from 'vue'
import { useRoute, useRouter, type LocationQueryValue } from 'vue-router'
import { adminError } from '../api/adminResources'
import { supportApi } from '../api/support'
import { useAdminQuery } from '../composables/useAdminQuery'
import {
  categoryLabels, priorityLabels, supportTime, ticketStatusLabels,
  type AdminTicketPage, type NewTicket, type TicketCategory, type TicketPriority, type TicketStatus, type TicketSummary,
} from '../types/support'

const props = defineProps<{ operator?: boolean }>()
const router = useRouter()
const route = useRoute()
const page = ref(1)
const filters = reactive({
  status: '' as TicketStatus | '', category: '' as TicketCategory | '',
  assignee_id: '', priority: '' as TicketPriority | '',
})
const { data, loading, error, load } = useAdminQuery(signal => props.operator
  ? supportApi.adminTickets({ ...filters, page: page.value }, signal)
  : supportApi.myTickets(page.value, signal))
const assignees = computed(() => props.operator ? (data.value as AdminTicketPage | undefined)?.assignees ?? [] : [])
const formOpen = ref(false)
const formError = ref('')
const submitting = ref(false)
const form = reactive<NewTicket>({ category: 'inquiry', subject: '', content: '' })
let submitRequest: AbortController | undefined

function readOption<T extends string>(value: LocationQueryValue | LocationQueryValue[], options: Record<T, string>): T | '' {
  return typeof value === 'string' && Object.hasOwn(options, value) ? value as T : ''
}

watch(() => route.query, query => {
  if (!props.operator || route.name !== 'admin-tickets') return
  filters.status = readOption(query.status, ticketStatusLabels)
  filters.category = readOption(query.category, categoryLabels)
  filters.priority = readOption(query.priority, priorityLabels)
  filters.assignee_id = typeof query.assignee_id === 'string' && query.assignee_id.length <= 36 ? query.assignee_id : ''
  page.value = 1
  void load()
}, { immediate: true })
onMounted(() => { if (!props.operator) void load() })
onScopeDispose(() => submitRequest?.abort())

function search() {
  const query = {
    ...route.query,
    status: filters.status || undefined, category: filters.category || undefined,
    assignee_id: filters.assignee_id || undefined, priority: filters.priority || undefined,
  }
  const next = { name: 'admin-tickets', query }
  if (router.resolve(next).fullPath !== route.fullPath) {
    void router.push(next)
    return
  }
  page.value = 1
  void load()
}

function resetFilters() {
  Object.assign(filters, { status: '', category: '', assignee_id: '', priority: '' })
  search()
}

function details(row: TicketSummary) {
  return { name: props.operator ? 'admin-ticket-detail' : 'my-ticket-detail', params: { id: row.id } }
}

async function submit() {
  if (submitting.value) return
  formError.value = ''
  if (!form.subject.trim() || !form.content.trim()) {
    formError.value = '请填写主题和内容。'
    return
  }
  submitting.value = true
  const request = new AbortController()
  submitRequest = request
  try {
    const ticket = await supportApi.submit(form, request.signal)
    if (request.signal.aborted) return
    formOpen.value = false
    form.subject = ''
    form.content = ''
    await router.push(details(ticket))
  } catch (failure) {
    if (!request.signal.aborted) formError.value = adminError(failure)
  } finally {
    if (submitRequest === request) submitting.value = false
  }
}
</script>

<template>
  <section class="resource-page support-page">
    <header class="resource-titlebar support-title">
      <h1>{{ operator ? '客服工单' : '我的工单' }}</h1>
      <el-button v-if="!operator" type="primary" @click="formOpen = true">提交工单</el-button>
    </header>
    <div class="resource-panel">
      <form v-if="operator" class="resource-toolbar" @submit.prevent="search">
        <el-select v-model="filters.status" aria-label="按状态筛选" placeholder="全部状态" clearable value-on-clear="" @change="search">
          <el-option v-for="(label, value) in ticketStatusLabels" :key="value" :value="value" :label="value === 'new' ? '待接单' : label" />
        </el-select>
        <el-select v-model="filters.category" aria-label="按分类筛选" placeholder="全部分类" clearable value-on-clear="" @change="search">
          <el-option v-for="(label, value) in categoryLabels" :key="value" :value="value" :label="label" />
        </el-select>
        <el-select v-model="filters.assignee_id" aria-label="按负责人筛选" placeholder="所有负责人" clearable value-on-clear="" @change="search">
          <el-option value="unassigned" label="未分配" />
          <el-option v-for="account in assignees" :key="account.id" :value="account.id" :label="account.username" />
        </el-select>
        <el-select v-model="filters.priority" aria-label="按优先级筛选" placeholder="全部优先级" clearable value-on-clear="" @change="search">
          <el-option v-for="(label, value) in priorityLabels" :key="value" :value="value" :label="label" />
        </el-select>
        <el-button native-type="submit" :loading="loading">查询</el-button>
        <el-button @click="resetFilters">清空筛选</el-button>
      </form>
      <div v-if="error" class="resource-stack support-error">
        <el-alert :title="error" type="error" :closable="false" show-icon />
        <div><el-button @click="load">重试</el-button></div>
      </div>
      <el-table v-if="operator && (data || !error)" v-loading="loading" :data="data?.items ?? []"
        row-key="id" empty-text="暂无匹配的工单">
        <el-table-column label="主题与工单号" min-width="230">
          <template #default="{ row }">
            <router-link class="resource-link" :to="details(row)">{{ row.subject }}</router-link>
            <p class="resource-muted ticket-number">{{ row.number }}</p>
          </template>
        </el-table-column>
        <el-table-column label="分类" width="80">
          <template #default="{ row }">{{ categoryLabels[row.category as TicketCategory] }}</template>
        </el-table-column>
        <el-table-column label="状态" width="98">
          <template #default="{ row }">{{ ticketStatusLabels[row.status as TicketStatus] }}</template>
        </el-table-column>
        <el-table-column label="优先级" width="80">
          <template #default="{ row }">{{ priorityLabels[row.priority as keyof typeof priorityLabels] }}</template>
        </el-table-column>
        <el-table-column label="负责人" min-width="100">
          <template #default="{ row }">{{ row.assignee?.username ?? '待接单' }}</template>
        </el-table-column>
        <el-table-column label="更新时间" min-width="142">
          <template #default="{ row }">{{ supportTime(row.updated_at) }}</template>
        </el-table-column>
      </el-table>
      <template v-if="!operator">
        <p v-if="loading && !data" role="status">正在加载工单…</p>
        <p v-else-if="data && !data.items.length" class="support-empty">暂无工单</p>
        <ul v-else-if="data" class="tourist-tickets">
          <li v-for="row in data.items" :key="row.id">
            <div class="resource-actions">
              <router-link class="resource-link" :to="details(row)">{{ row.subject }}</router-link>
              <el-tag size="small">{{ ticketStatusLabels[row.status] }}</el-tag>
            </div>
            <p class="resource-muted ticket-number">{{ categoryLabels[row.category] }} · {{ row.number }}</p>
            <p class="resource-muted">更新于 {{ supportTime(row.updated_at) }}</p>
          </li>
        </ul>
      </template>
      <div v-if="data && (operator || data.total > 20)" class="resource-pagination">
        <el-pagination v-model:current-page="page" :page-size="20" :total="data.total"
          layout="total, prev, pager, next" @current-change="load" />
      </div>
    </div>

    <el-dialog v-if="!operator" v-model="formOpen" title="提交工单" class="resource-dialog" width="520px"
      :close-on-click-modal="!submitting" :close-on-press-escape="!submitting" :show-close="!submitting">
      <el-alert v-if="formError" class="support-error" :title="formError" type="error" :closable="false" show-icon />
      <el-form label-position="top" :disabled="submitting" @submit.prevent="submit">
        <el-form-item label="分类">
          <el-select v-model="form.category" aria-label="工单分类">
            <el-option v-for="(label, value) in categoryLabels" :key="value" :value="value" :label="label" />
          </el-select>
        </el-form-item>
        <el-form-item label="主题" required>
          <el-input v-model="form.subject" :maxlength="100" />
        </el-form-item>
        <el-form-item label="内容" required>
          <el-input v-model="form.content" type="textarea" :rows="5" :maxlength="4000" show-word-limit />
        </el-form-item>
        <div class="resource-actions">
          <el-button @click="formOpen = false">取消</el-button>
          <el-button type="primary" native-type="submit" :loading="submitting">提交工单</el-button>
        </div>
      </el-form>
    </el-dialog>
  </section>
</template>

<style scoped>
.ticket-number { overflow-wrap: anywhere; }
.tourist-tickets { list-style: none; }
.tourist-tickets li { padding: 13px 0; border-bottom: 1px solid #e3e9f2; }
.tourist-tickets li:first-child { padding-top: 0; }
.tourist-tickets li:last-child { border-bottom: 0; padding-bottom: 0; }
.tourist-tickets p { margin-top: 5px; }
</style>

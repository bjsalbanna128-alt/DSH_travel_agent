<script setup lang="ts">
import { computed, onMounted, onScopeDispose, ref, shallowRef, watch } from 'vue'
import { useRoute, type RouteLocationRaw } from 'vue-router'
import { adminError } from '../api/adminResources'
import {
  formatYuan, getDashboard, getDashboardTrends,
  type AdminDashboard, type AdminTrends,
} from '../api/dashboard'
import BusinessTrendChart from '../components/BusinessTrendChart.vue'
import CategoryBars from '../components/CategoryBars.vue'
import { useAuthStore } from '../stores/auth'
import { useInboxStore } from '../stores/inbox'
import { categoryLabels } from '../types/support'

const POLL_MS = 30_000
const MERGE_WINDOW_MS = 250
const auth = useAuthStore()
const inbox = useInboxStore()
const route = useRoute()
const data = shallowRef<AdminDashboard>()
const error = ref('')
const loading = ref(false)
let pending: AbortController | undefined
let timer: number | undefined
let lastStarted = -Infinity
let mounted = false
const formatter = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', dateStyle: 'medium', timeStyle: 'medium',
})
const formatTime = (value: string) => formatter.format(new Date(value))

const eligible = () => mounted && route.name === 'admin-home' && auth.role === 'operator'
const overview = computed(() => {
  const stats = data.value?.overview
  if (!stats) return []
  return [
    { label: '已确认行程', value: stats.confirmed_trips, to: { name: 'admin-trips' } },
    { label: '游客会员', value: stats.tourist_members, note: `今日新增会员 ${stats.new_members_today}`, to: { name: 'admin-members' } },
    { label: '行程模板', value: stats.templates_total, note: `其中已发布 ${stats.templates_published}`, to: { name: 'admin-itinerary-templates' } },
    { label: '推荐内容', value: stats.recommendations_total, note: `其中已发布 ${stats.recommendations_published}`, to: { name: 'admin-recommendations' } },
  ]
})

const unassigned = { status: 'new', assignee_id: 'unassigned' }
const work = computed(() => {
  const stats = data.value?.work
  if (!stats) return []
  const items: { label: string; value: number; scope: string; alert?: boolean; to: RouteLocationRaw }[] = [
    { label: '待接单', value: stats.unassigned_tickets, scope: '全企业', to: { name: 'admin-tickets', query: unassigned } },
    { label: '我处理中', value: stats.my_processing_tickets, scope: '我的',
      to: { name: 'admin-tickets', query: { status: 'processing', assignee_id: auth.userId } } },
    { label: '高优先级待接单', value: stats.high_unassigned_tickets, scope: '全企业', alert: true,
      to: { name: 'admin-tickets', query: { ...unassigned, priority: 'high' } } },
    { label: '我的未读消息', value: inbox.unread, scope: '我的', alert: true,
      to: { name: 'admin-messages', query: { unread_only: 'true' } } },
  ]
  return items
})

async function refresh(force: boolean) {
  if (pending || (!force && performance.now() - lastStarted < MERGE_WINDOW_MS)) return
  const request = new AbortController()
  const applyUnread = inbox.dashboardUnreadReceiver()
  pending = request
  lastStarted = performance.now()
  loading.value = true
  try {
    const result = await getDashboard(request.signal)
    if (request.signal.aborted || !eligible()) return
    applyUnread(result.work.my_unread_messages)
    data.value = result
    error.value = ''
  } catch (failure) {
    if (!request.signal.aborted && eligible()) error.value = adminError(failure)
  } finally {
    if (pending === request) {
      pending = undefined
      loading.value = false
    }
  }
}

function schedule(force = false) {
  window.clearTimeout(timer)
  if (!eligible() || document.hidden) return
  void refresh(force)
  timer = window.setTimeout(onForeground, POLL_MS)
}

const trends = shallowRef<AdminTrends>()
const trendDays = ref<7 | 30>(7)
const trendLoading = ref(false)
const trendError = ref('')
let trendPending: AbortController | undefined

async function loadTrends(days: 7 | 30 = trendDays.value) {
  trendPending?.abort()
  const request = new AbortController()
  trendPending = request
  trendLoading.value = true
  try {
    const payload = await getDashboardTrends(days, request.signal)
    if (request.signal.aborted) return
    trends.value = payload
    trendError.value = ''
  } catch (failure) {
    if (!request.signal.aborted) trendError.value = adminError(failure)
  } finally {
    if (trendPending === request) {
      trendPending = undefined
      trendLoading.value = false
    }
  }
}

function switchTrendDays(value: string | number | boolean | undefined) {
  trendDays.value = value === 30 ? 30 : 7
  void loadTrends()
}

const readyRate = computed(() => {
  const stats = trends.value?.totals
  if (!stats?.fulfillment_total) return '—'
  return `${Math.round((trends.value!.series.reduce((sum, row) => sum + row.fulfillment_ready, 0)
    / stats.fulfillment_total) * 100)}%`
})

const keyNumbers = computed(() => {
  const stats = trends.value?.totals
  if (!stats) return []
  return [
    { label: '净收款', value: formatYuan(stats.net_fen), negative: stats.net_fen < 0 },
    { label: '订单数', value: stats.orders.toLocaleString() },
    { label: '客单价', value: formatYuan(stats.avg_order_fen) },
    { label: '履约就绪率', value: readyRate.value },
  ]
})

const trendRows = computed(() => {
  const payload = trends.value
  if (!payload) return []
  return [...payload.series].reverse().map(row => ({
    ...row,
    isToday: row.date === payload.today,
  }))
})

const trendsEmpty = computed(() => {
  const stats = trends.value?.totals
  if (!stats) return false
  return stats.paid_fen === 0 && stats.refund_fen === 0 && stats.fulfillment_total === 0
})

function handleRefresh() {
  schedule(true)
  void loadTrends()
}

function onForeground() { schedule() }

function clear() {
  window.clearTimeout(timer)
  pending?.abort()
  pending = undefined
  lastStarted = -Infinity
  data.value = undefined
  error.value = ''
  loading.value = false
}

watch([() => auth.sessionVersion, () => auth.userId, () => auth.role], () => {
  clear()
  schedule()
}, { flush: 'sync' })

onMounted(() => {
  mounted = true
  document.addEventListener('visibilitychange', onForeground)
  window.addEventListener('focus', onForeground)
  schedule()
  void loadTrends()
})
onScopeDispose(() => {
  mounted = false
  trendPending?.abort()
  document.removeEventListener('visibilitychange', onForeground)
  window.removeEventListener('focus', onForeground)
  clear()
})
</script>

<template>
  <div class="resource-page dashboard">
    <header class="resource-titlebar support-title">
      <div>
        <h1>工作台</h1>
        <p v-if="data" class="resource-muted updated">
          最近更新 <time :datetime="data.as_of">{{ formatTime(data.as_of) }}</time>（北京时间）
        </p>
      </div>
      <el-button :loading="loading" @click="handleRefresh">刷新工作台</el-button>
    </header>

    <el-alert v-if="error" :title="data ? '刷新失败，当前显示上次成功获取的数据。' : '工作台加载失败'"
      :description="error" :type="data ? 'warning' : 'error'" :closable="false" show-icon class="support-error" />
    <p v-else-if="loading && !data" class="resource-panel" role="status">正在加载工作台…</p>

    <template v-if="data">
      <section aria-labelledby="overview-title" class="dashboard-section">
        <h2 id="overview-title">经营概览</h2>
        <div class="dashboard-grid">
          <router-link v-for="card in overview" :key="card.label" :to="card.to" class="metric">
            <span class="metric-label">{{ card.label }}</span>
            <strong>{{ card.value.toLocaleString() }}</strong>
            <span v-if="card.note" class="metric-note">{{ card.note }}</span>
          </router-link>
        </div>
      </section>

      <section aria-labelledby="trends-title" class="dashboard-section">
        <div class="dashboard-subhead">
          <h2 id="trends-title">经营数据</h2>
          <el-radio-group :model-value="trendDays" size="small"
            @update:model-value="switchTrendDays">
            <el-radio-button :value="7">近 7 天</el-radio-button>
            <el-radio-button :value="30">近 30 天</el-radio-button>
          </el-radio-group>
        </div>

        <div v-if="trendError" class="resource-panel">
          <el-alert :title="trends ? '经营数据刷新失败，当前显示上次成功获取的数据。' : '经营数据加载失败'"
            :description="trendError" :type="trends ? 'warning' : 'error'" :closable="false" show-icon />
          <p><el-button size="small" @click="loadTrends()">重试</el-button></p>
        </div>
        <p v-else-if="trendLoading && !trends" class="resource-panel" role="status">正在加载经营数据…</p>

        <template v-if="trends">
          <p class="resource-muted trend-range">
            {{ trends.from }} 至 {{ trends.to }}（北京时间，含今日）
          </p>
          <div class="dashboard-grid">
            <div v-for="item in keyNumbers" :key="item.label" class="metric">
              <span class="metric-label">{{ item.label }}</span>
              <strong :class="{ 'value-negative': item.negative }"
                :title="item.negative ? '当日退款大于收款' : undefined">{{ item.value }}</strong>
            </div>
          </div>

          <p v-if="trendsEmpty" class="resource-panel support-empty">
            这段时间还没有成交，也没有需要履约的服务。
          </p>
          <template v-else>
            <div class="trend-panels">
              <div class="resource-panel">
                <h3>每日收款与退款</h3>
                <BusinessTrendChart :series="trends.series" :today="trends.today" />
              </div>
              <div class="resource-panel">
                <h3>品类构成</h3>
                <CategoryBars :items="trends.by_category" />
              </div>
            </div>

            <div class="resource-panel trend-table">
              <el-table :data="trendRows" size="small" row-key="date" max-height="320">
                <el-table-column label="日期" width="150">
                  <template #default="{ row }">
                    {{ row.date }}
                    <el-tag v-if="row.isToday" size="small" type="warning">进行中</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="收款" width="120">
                  <template #default="{ row }">{{ formatYuan(row.paid_fen) }}</template>
                </el-table-column>
                <el-table-column label="退款" width="120">
                  <template #default="{ row }">{{ formatYuan(row.refund_fen) }}</template>
                </el-table-column>
                <el-table-column label="净收款" width="130">
                  <template #default="{ row }">
                    <span :class="{ 'value-negative': row.net_fen < 0 }"
                      :title="row.net_fen < 0 ? '当日退款大于收款' : undefined">
                      {{ formatYuan(row.net_fen) }}
                    </span>
                  </template>
                </el-table-column>
                <el-table-column prop="orders" label="订单数" width="90" />
                <el-table-column prop="fulfillment_total" label="履约任务" width="100" />
                <el-table-column label="车队占用" width="120">
                  <template #default="{ row }">
                    {{ row.fleet_used }} / {{ row.fleet_capacity }}
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </template>
        </template>
      </section>

      <section aria-labelledby="work-title" class="dashboard-section">
        <div class="dashboard-subhead">
          <h2 id="work-title">待办与预警</h2>
          <p class="resource-muted">今日新工单 {{ data.work.new_tickets_today.toLocaleString() }}</p>
        </div>
        <div class="dashboard-grid">
          <router-link v-for="item in work" :key="item.label" :to="item.to"
            :class="['metric', { 'metric-alert': item.alert && item.value > 0 }]">
            <span class="metric-label">{{ item.label }}</span>
            <strong>{{ item.value.toLocaleString() }}</strong>
            <span class="metric-note">{{ item.scope }}</span>
          </router-link>
        </div>
        <div class="resource-panel priority-panel">
          <h3>高优先级待接工单</h3>
          <p v-if="!data.high_priority_items.length" class="support-empty">暂无高优先级待接工单</p>
          <ul v-else class="priority-list">
            <li v-for="ticket in data.high_priority_items" :key="ticket.id">
              <router-link :to="{ name: 'admin-ticket-detail', params: { id: ticket.id } }" class="priority-row resource-link">
                <strong>{{ ticket.number }}</strong>
                <span>{{ categoryLabels[ticket.category] }}</span>
                <time :datetime="ticket.created_at">{{ formatTime(ticket.created_at) }}</time>
              </router-link>
            </li>
          </ul>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.dashboard { max-width: 1160px; }
.dashboard-section { margin-top: 26px; }
.dashboard-section h2 { font-size: 20px; margin-bottom: 12px; }
.updated { margin-top: 6px; }
.dashboard-subhead { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; }
.dashboard-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.metric {
  display: flex; flex-direction: column; align-items: flex-start; gap: 6px;
  min-width: 0; padding: 16px; border: 1px solid #dbe4ee; border-radius: 8px;
  background: #fff; color: #182940; text-decoration: none;
}
.metric:hover, .priority-row:hover { border-color: #6b92b9; background: #f5f9ff; }
.metric:focus-visible, .priority-row:focus-visible { outline: 2px solid #255b90; outline-offset: 2px; }
.metric-label { font-weight: 650; font-size: .92rem; }
.metric strong { font-size: 1.8rem; line-height: 1.16; font-variant-numeric: tabular-nums; }
.metric-note { color: #4a5e73; font-size: .82rem; }
.metric-alert { color: #8b2d18; background: #fff5ee; border-color: #ebc6ae; }
.metric-alert:hover { background: #ffecde; border-color: #b57552; }
.value-negative { color: #c0392b; }
.trend-range { margin-bottom: 8px; }
.trend-panels { display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); gap: 12px; margin-top: 12px; }
.trend-panels h3 { font-size: 1.03rem; margin-bottom: 8px; }
.trend-table { margin-top: 12px; }
.priority-panel { margin-top: 14px; }
.priority-panel h3 { font-size: 1.03rem; }
.priority-list { list-style: none; margin-top: 8px; }
.priority-list li + li { border-top: 1px solid #e6ebf2; }
.priority-row { display: grid; grid-template-columns: 2fr 1fr auto; gap: 6px 14px; padding: 10px 5px; overflow-wrap: anywhere; }
.priority-row time { color: #4a5e73; }
@media (max-width: 880px) {
  .dashboard-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .trend-panels { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 450px) {
  .metric { padding: 11px; }
  .priority-row { grid-template-columns: 1fr; }
}
</style>

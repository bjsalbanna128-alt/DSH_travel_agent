<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTravelStore } from '../stores/travel'
import { decideTrip, getTrip } from '../api/travel'
import MiniMap from '../components/MiniMap.vue'
import { itineraryBudget } from '../itineraryBudget'
import type { DayPlan, TripRecord } from '../types/travel'

const route = useRoute()
const router = useRouter()
const store = useTravelStore()

const tripId = computed(() => route.params.tripId as string)
const activeDay = ref(1)
const loading = ref(false)
const trip = ref<TripRecord | null>(null)
const isDraft = computed(() => trip.value?.status === 'draft')
const feedback = ref('')
const deciding = ref(false)
const decisionError = ref('')
const notice = ref('')

const itinerary = computed(() => trip.value?.itinerary)
const dayPlans = computed(() => itinerary.value?.day_plans ?? [])

const currentDay = computed<DayPlan | null>(() =>
  dayPlans.value.find(d => d.day === activeDay.value) ?? null
)

const isEmpty = computed(() =>
  !loading.value && (!itinerary.value || dayPlans.value.length === 0)
)

watch(tripId, async (id, _, onCleanup) => {
  trip.value = null
  feedback.value = ''
  decisionError.value = ''
  notice.value = ''
  deciding.value = false
  activeDay.value = 1
  if (!id) return
  const controller = new AbortController()
  onCleanup(() => controller.abort())
  loading.value = true
  try {
    const saved = await getTrip(id, controller.signal)
    if (!controller.signal.aborted) trip.value = saved
  } catch (e: unknown) {
    if (!controller.signal.aborted) console.error('Failed to load trip:', e)
  } finally {
    if (!controller.signal.aborted) loading.value = false
  }
}, { immediate: true })

async function submitDecision(action: 'approve' | 'adjust') {
  if (!trip.value || deciding.value) return
  const id = trip.value.id
  deciding.value = true
  decisionError.value = ''
  notice.value = ''
  try {
    const saved = await decideTrip(id, action, trip.value.version, feedback.value.trim())
    if (tripId.value !== id) return
    trip.value = saved
    if (store.currentTripId === id) {
      store.itinerary = saved.itinerary
      store.dayPlans = saved.itinerary.day_plans
      if (saved.status === 'completed') store.pendingApproval = null
    }
    feedback.value = ''
    notice.value = action === 'adjust' ? '已更新草稿，请查看后确认。' : '行程已确认。'
  } catch (error) {
    if (tripId.value === id) {
      decisionError.value = error instanceof Error ? error.message : '提交失败，请重试'
    }
  } finally {
    if (tripId.value === id) deciding.value = false
  }
}

function formatPrice(v: number): string {
  return v > 0 ? `¥${v.toLocaleString()}` : '—'
}

const categoryTag = (cat: string) => {
  const map: Record<string, string> = {
    cultural: '文化', natural: '自然', entertainment: '娱乐', shopping: '购物',
  }
  return map[cat] || cat
}

const budgetItems = computed(() => {
  if (!dayPlans.value.length) return []
  const budget = itineraryBudget(dayPlans.value, trip.value?.travel_request)
  const other = (itinerary.value?.total_budget_estimate_cny ?? budget.total) - budget.total
  const items = [
    { label: '景点门票', value: budget.tickets },
    { label: '住宿', value: budget.hotels },
    { label: '餐饮', value: budget.meals },
    { label: '交通', value: budget.transport },
  ]
  if (other > 0.005) items.push({ label: '其他预估费用', value: other })
  return items
})
</script>

<template>
  <div class="trip-detail">
    <!-- Loading -->
    <div v-if="loading" class="empty-state">
      <el-icon class="is-loading" :size="32"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="3" stroke-dasharray="31.4 31.4" stroke-linecap="round"/></svg></el-icon>
      <p>加载中...</p>
    </div>

    <!-- Empty state -->
    <div v-else-if="isEmpty" class="empty-state">
      <el-empty description="暂无行程数据">
        <el-button type="primary" @click="router.push('/')">去规划一个旅行</el-button>
      </el-empty>
    </div>

    <template v-else>
      <!-- Header card -->
      <div class="trip-header">
        <div class="header-left">
          <el-button text @click="router.push('/plan')">← 返回规划</el-button>
          <h1>{{ itinerary?.title || '行程详情' }}</h1>
          <div class="header-meta">
            <el-tag type="primary">{{ itinerary?.destination }}</el-tag>
            <el-tag :type="isDraft ? 'warning' : 'success'">{{ isDraft ? '待确认' : '已确认' }}</el-tag>
            <span>{{ itinerary?.duration_days }} 天</span>
            <span v-if="itinerary?.version">版本 {{ itinerary?.version }}</span>
            <span>{{ itinerary?.created_at?.slice(0, 10) }}</span>
          </div>
        </div>
        <div class="header-budget">
          <div class="budget-amount">{{ formatPrice(itinerary?.total_budget_estimate_cny ?? 0) }}</div>
          <div class="budget-sub">预估总费用</div>
          <el-button v-if="!isDraft" type="primary" plain size="small" style="margin-top:8px" @click="router.push(`/trip/${tripId}/edit`)">
            编辑行程
          </el-button>
        </div>
      </div>

      <el-alert v-if="notice" :title="notice" type="success" :closable="false" class="review-panel" />
      <el-card v-if="isDraft" class="review-panel" shadow="never">
        <el-input
          v-model="feedback"
          aria-label="AI 调整意见"
          type="textarea"
          :rows="2"
          maxlength="2000"
          :disabled="deciding"
          placeholder="例如：第三天太满了，删掉杜甫草堂"
        />
        <el-alert v-if="decisionError" :title="decisionError" type="error" :closable="false" />
        <div class="review-actions">
          <el-button :disabled="deciding || !feedback.trim()" @click="submitDecision('adjust')">
            提交 AI 调整
          </el-button>
          <el-button type="primary" :disabled="deciding" @click="submitDecision('approve')">
            确认行程
          </el-button>
          <span v-if="deciding" role="status">正在处理…</span>
        </div>
      </el-card>

      <el-row :gutter="24">
        <!-- Main content -->
        <el-col :span="16">
          <!-- Day tabs -->
          <el-tabs v-model="activeDay" class="day-tabs">
            <el-tab-pane
              v-for="dp in dayPlans"
              :key="dp.day"
              :label="`Day ${dp.day}`"
              :name="dp.day"
            >
              <div v-if="currentDay" class="day-content">
                <!-- Attractions -->
                <div class="day-section">
                  <h3>景点</h3>
                  <div
                    v-for="a in currentDay.attractions"
                    :key="a.id || a.name"
                    class="attr-card"
                  >
                    <div class="attr-header">
                      <span class="attr-name">{{ a.name }}</span>
                      <el-tag size="small" :type="a.category === 'natural' ? 'success' : a.category === 'entertainment' ? 'warning' : ''">
                        {{ categoryTag(a.category) }}
                      </el-tag>
                    </div>
                    <p class="attr-desc">{{ a.description }}</p>
                    <div class="attr-meta">
                      <span>游玩 {{ a.visit_duration_hours }}h</span>
                      <span>评分 {{ a.rating }}</span>
                      <span>门票 {{ formatPrice(a.ticket_price_cny) }}</span>
                      <span v-if="a.opening_hours">{{ a.opening_hours }}</span>
                    </div>
                  </div>
                </div>

                <!-- Route -->
                <div v-if="currentDay.route" class="day-section">
                  <h3>路线</h3>
                  <div class="route-info">
                    <span>交通方式：{{ currentDay.route.travel_mode === 'metro' ? '地铁' : currentDay.route.travel_mode === 'bus' ? '公交' : currentDay.route.travel_mode === 'taxi' ? '打车' : '步行' }}</span>
                    <span>预计距离：{{ currentDay.route.total_distance_km }}km</span>
                    <span>预计耗时：{{ currentDay.route.estimated_travel_time_minutes }}分钟</span>
                  </div>
                </div>

                <!-- Meals -->
                <div v-if="currentDay.lunch || currentDay.dinner" class="day-section">
                  <h3>餐饮</h3>
                  <div class="meal-cards">
                    <div v-if="currentDay.lunch" class="meal-card">
                      <div class="meal-label">午餐</div>
                      <div class="meal-name">{{ currentDay.lunch.name }}</div>
                      <div class="meal-meta">
                        <span>{{ currentDay.lunch.cuisine }}</span>
                        <span>{{ formatPrice(currentDay.lunch.avg_price_per_person_cny) }}/人</span>
                        <span>评分 {{ currentDay.lunch.rating }}</span>
                      </div>
                    </div>
                    <div v-if="currentDay.dinner" class="meal-card">
                      <div class="meal-label">晚餐</div>
                      <div class="meal-name">{{ currentDay.dinner.name }}</div>
                      <div class="meal-meta">
                        <span>{{ currentDay.dinner.cuisine }}</span>
                        <span>{{ formatPrice(currentDay.dinner.avg_price_per_person_cny) }}/人</span>
                        <span>评分 {{ currentDay.dinner.rating }}</span>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- Hotel -->
                <div v-if="currentDay.hotel" class="day-section">
                  <h3>住宿</h3>
                  <div class="hotel-card">
                    <div class="hotel-name">{{ currentDay.hotel.name }}</div>
                    <div class="hotel-meta">
                      <span>{{ currentDay.hotel.area }}</span>
                      <span>{{ formatPrice(currentDay.hotel.price_per_night_cny) }}/晚</span>
                      <span>评分 {{ currentDay.hotel.rating }}</span>
                    </div>
                    <div v-if="currentDay.hotel.amenities?.length" class="amenities">
                      <el-tag
                        v-for="a in currentDay.hotel.amenities"
                        :key="a"
                        size="small"
                        class="amenity-tag"
                      >
                        {{ a }}
                      </el-tag>
                    </div>
                  </div>
                </div>

                <!-- Transport -->
                <div v-if="currentDay.transport?.length" class="day-section">
                  <h3>交通</h3>
                  <div v-for="(t, i) in currentDay.transport" :key="i" class="transport-item">
                    <span>{{ t.from_location }} → {{ t.to_location }}</span>
                    <span>{{ t.type }}</span>
                    <span>{{ t.departure_time }} - {{ t.arrival_time }}</span>
                    <span>{{ formatPrice(t.price_cny) }}/人</span>
                  </div>
                </div>

                <!-- Notes -->
                <div v-if="currentDay.notes" class="day-notes">
                  {{ currentDay.notes }}
                </div>
              </div>
            </el-tab-pane>
          </el-tabs>

          <!-- Overall tips -->
          <div v-if="itinerary?.overall_tips" class="tips-section">
            <h3>旅行贴士</h3>
            <p>{{ itinerary.overall_tips }}</p>
          </div>
        </el-col>

        <!-- Sidebar -->
        <el-col :span="8">
          <!-- Map -->
          <MiniMap v-if="dayPlans.length > 0" :day-plans="dayPlans" />

          <!-- Budget breakdown -->
          <div class="budget-card">
            <h3>费用明细</h3>
            <div v-for="item in budgetItems" :key="item.label" class="budget-row">
              <span class="budget-row-label">{{ item.label }}</span>
              <span class="budget-row-value">{{ formatPrice(item.value) }}</span>
            </div>
            <el-divider />
            <div class="budget-row budget-row-total">
              <span>合计</span>
              <span>{{ formatPrice(itinerary?.total_budget_estimate_cny ?? 0) }}</span>
            </div>
          </div>
        </el-col>
      </el-row>
    </template>
  </div>
</template>

<style scoped>
.review-panel { margin-bottom: 20px; }
.review-actions { display: flex; align-items: center; gap: 10px; margin-top: 12px; }
.trip-detail { max-width: 1200px; margin: 0 auto; padding: 0 16px; }

/* Header */
.trip-header {
  display: flex; justify-content: space-between; align-items: flex-start;
  background: #fff; border-radius: 12px; padding: 24px; margin-bottom: 24px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06);
}
.header-left h1 { margin: 8px 0 12px; font-size: 24px; }
.header-meta { display: flex; gap: 12px; align-items: center; font-size: 14px; color: #606266; }
.header-budget { text-align: center; }
.budget-amount { font-size: 28px; font-weight: 700; color: #67c23a; }
.budget-sub { font-size: 12px; color: #909399; margin-top: 4px; }

/* Day content */
.day-tabs { background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.day-content { min-height: 300px; }
.day-section { margin-bottom: 20px; }
.day-section h3 { font-size: 16px; color: #303133; margin-bottom: 12px; padding-bottom: 6px; border-bottom: 1px solid #ebeef5; }

/* Attraction cards */
.attr-card { background: #f5f7fa; border-radius: 8px; padding: 12px; margin-bottom: 8px; }
.attr-header { display: flex; justify-content: space-between; align-items: center; }
.attr-name { font-weight: 600; font-size: 15px; }
.attr-desc { font-size: 13px; color: #606266; margin: 6px 0; }
.attr-meta { display: flex; gap: 12px; font-size: 12px; color: #909399; }

/* Route */
.route-info { display: flex; gap: 16px; font-size: 14px; color: #606266; }

/* Meals */
.meal-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.meal-card { background: #fdf6ec; border-radius: 8px; padding: 12px; }
.meal-label { font-size: 12px; color: #e6a23c; margin-bottom: 4px; }
.meal-name { font-weight: 600; font-size: 14px; margin-bottom: 4px; }
.meal-meta { display: flex; gap: 8px; font-size: 12px; color: #909399; }

/* Hotel */
.hotel-card { background: #ecf5ff; border-radius: 8px; padding: 12px; }
.hotel-name { font-weight: 600; font-size: 14px; }
.hotel-meta { display: flex; gap: 12px; font-size: 13px; color: #606266; margin: 6px 0; }
.amenities { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 6px; }
.amenity-tag { margin-right: 0 !important; }

/* Transport */
.transport-item {
  display: flex; gap: 12px; align-items: center; padding: 6px 0;
  font-size: 13px; color: #606266;
}

/* Notes */
.day-notes { background: #fef0f0; border-radius: 8px; padding: 10px 14px; font-size: 13px; color: #f56c6c; margin-top: 12px; }

/* Tips */
.tips-section {
  background: #fff; border-radius: 12px; padding: 20px; margin-top: 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06);
}
.tips-section h3 { font-size: 16px; margin-bottom: 8px; }
.tips-section p { font-size: 14px; color: #606266; line-height: 1.8; }

/* Budget sidebar */
.budget-card {
  background: #fff; border-radius: 12px; padding: 16px; margin-top: 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06);
}
.budget-card h3 { font-size: 15px; margin-bottom: 12px; }
.budget-row { display: flex; justify-content: space-between; padding: 6px 0; font-size: 14px; color: #606266; }
.budget-row-total { font-weight: 700; font-size: 16px; color: #303133; }

/* Empty */
.empty-state { display: flex; justify-content: center; align-items: center; min-height: 400px; }
</style>

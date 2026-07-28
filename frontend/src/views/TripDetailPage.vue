<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTravelStore } from '../stores/travel'
import { getTrip } from '../api/travel'
import MiniMap from '../components/MiniMap.vue'
import type { DayPlan } from '../types/travel'

const route = useRoute()
const router = useRouter()
const store = useTravelStore()

const tripId = route.params.tripId as string
const activeDay = ref(1)
const loading = ref(false)

const itinerary = computed(() => store.itinerary)
const dayPlans = computed(() => store.dayPlans)

const currentDay = computed<DayPlan | null>(() =>
  dayPlans.value.find(d => d.day === activeDay.value) ?? null
)

const isEmpty = computed(() =>
  !loading.value && (!itinerary.value || dayPlans.value.length === 0)
)

onMounted(async () => {
  // If store is empty, load from API (e.g. coming from history page)
  if (!store.itinerary || store.dayPlans.length === 0) {
    loading.value = true
    try {
      const trip = await getTrip(tripId)
      if (trip.itinerary) {
        store.itinerary = trip.itinerary
        store.dayPlans = trip.itinerary.day_plans || []
        store.currentTripId = tripId
      }
    } catch (e: any) {
      console.error('Failed to load trip:', e)
    } finally {
      loading.value = false
    }
  }
})

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
  let tickets = 0, hotels = 0, meals = 0
  dayPlans.value.forEach(dp => {
    dp.attractions?.forEach(a => { tickets += a.ticket_price_cny || 0 })
    if (dp.hotel) hotels += dp.hotel.price_per_night_cny || 0
    if (dp.lunch) meals += dp.lunch.avg_price_per_person_cny || 0
    if (dp.dinner) meals += dp.dinner.avg_price_per_person_cny || 0
  })
  const total = itinerary.value?.total_budget_estimate_cny ?? tickets + hotels + meals
  return [
    { label: '景点门票', value: tickets },
    { label: '住宿', value: hotels },
    { label: '餐饮', value: meals },
    { label: '其他（交通/购物）', value: Math.max(0, total - tickets - hotels - meals) },
  ]
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
            <span>{{ itinerary?.duration_days }} 天</span>
            <span v-if="itinerary?.version">版本 {{ itinerary?.version }}</span>
            <span>{{ itinerary?.created_at?.slice(0, 10) }}</span>
          </div>
        </div>
        <div class="header-budget">
          <div class="budget-amount">{{ formatPrice(itinerary?.total_budget_estimate_cny ?? 0) }}</div>
          <div class="budget-sub">预估总费用</div>
          <el-button type="primary" plain size="small" style="margin-top:8px" @click="router.push(`/trip/${tripId}/edit`)">
            编辑行程
          </el-button>
        </div>
      </div>

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
                    <span>{{ formatPrice(t.price_cny) }}</span>
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

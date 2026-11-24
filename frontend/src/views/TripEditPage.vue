<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getTrip, updateTrip } from '../api/travel'
import { itineraryBudget } from '../itineraryBudget'
import type { DayPlan, Attraction, Hotel, Restaurant, Itinerary, TripRecord } from '../types/travel'

const route = useRoute()
const router = useRouter()

const tripId = route.params.tripId as string
const loading = ref(true)
const saving = ref(false)
const activeDay = ref(1)

const itinerary = ref<Itinerary | null>(null)
const dayPlans = ref<DayPlan[]>([])
const travelRequest = ref<TripRecord['travel_request']>()
const otherBudget = ref(0)

// Track drag state
const dragDay = ref(0)
const dragIndex = ref(-1)

// Add attraction dialog
const showAddAttr = ref(false)
const newAttraction = ref<Partial<Attraction>>({})

// Edit hotel dialog
const showEditHotel = ref(false)
const editHotel = ref<Partial<Hotel>>({})

// Edit restaurant dialog
const showEditMeal = ref(false)
const editMeal = ref<Partial<Restaurant>>({})
const editMealType = ref<'lunch' | 'dinner'>('lunch')
const editMealDay = ref(1)

const currentDay = computed<DayPlan | null>(() =>
  dayPlans.value.find(d => d.day === activeDay.value) ?? null
)

const budgetItems = computed(() => {
  const budget = itineraryBudget(dayPlans.value, travelRequest.value)
  return { ...budget, total: Math.round((budget.total + otherBudget.value) * 100) / 100 }
})

onMounted(async () => {
  loading.value = true
  try {
    const trip = await getTrip(tripId)
    if (trip.itinerary) {
      itinerary.value = trip.itinerary
      dayPlans.value = JSON.parse(JSON.stringify(trip.itinerary.day_plans || []))
      travelRequest.value = trip.travel_request
      otherBudget.value = Math.max(0, trip.itinerary.total_budget_estimate_cny
        - itineraryBudget(dayPlans.value, travelRequest.value).total)
    }
  } catch (e: any) {
    ElMessage.error('加载行程失败: ' + (e.message || '未知错误'))
  } finally {
    loading.value = false
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

// ── Drag & Drop ──────────────────────────────────────

function onDragStart(day: number, index: number, e: DragEvent) {
  dragDay.value = day
  dragIndex.value = index
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', `${day}:${index}`)
  }
}

function onDragOver(e: DragEvent) {
  e.preventDefault()
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'move'
}

function onDrop(day: number, e: DragEvent) {
  e.preventDefault()
  const targetEl = (e.target as HTMLElement).closest('.attr-edit-card') as HTMLElement | null
  if (!targetEl) return
  const parent = targetEl.parentElement
  if (!parent) return
  const cards = Array.from(parent.querySelectorAll(':scope > .attr-edit-card'))
  const targetIndex = cards.indexOf(targetEl)
  if (targetIndex < 0) return

  if (dragDay.value !== day) {
    // Cross-day move
    const srcDay = dayPlans.value.find(d => d.day === dragDay.value)
    const dstDay = dayPlans.value.find(d => d.day === day)
    if (!srcDay || !dstDay) return
    const [item] = srcDay.attractions.splice(dragIndex.value, 1)
    dstDay.attractions.splice(targetIndex, 0, item)
  } else if (dragIndex.value !== targetIndex) {
    // Same day reorder
    const dayPlan = dayPlans.value.find(d => d.day === day)
    if (!dayPlan) return
    const [item] = dayPlan.attractions.splice(dragIndex.value, 1)
    dayPlan.attractions.splice(targetIndex, 0, item)
  }
  dragDay.value = 0
  dragIndex.value = -1
}

function onDragEnd() {
  dragDay.value = 0
  dragIndex.value = -1
}

// ── Attraction actions ───────────────────────────────

function removeAttraction(day: number, index: number) {
  const dp = dayPlans.value.find(d => d.day === day)
  if (!dp) return
  dp.attractions.splice(index, 1)
}

function openAddAttraction(day: number) {
  activeDay.value = day
  newAttraction.value = {
    id: 'custom_' + Date.now(),
    name: '',
    category: 'cultural',
    description: '',
    rating: 4.0,
    visit_duration_hours: 2,
    ticket_price_cny: 0,
    location: { lat: 0, lng: 0 },
    opening_hours: '',
    tags: [],
    suitable_for: [],
    recommended_reason: '',
  }
  showAddAttr.value = true
}

function confirmAddAttraction() {
  if (!newAttraction.value.name?.trim()) {
    ElMessage.warning('请输入景点名称')
    return
  }
  const dp = dayPlans.value.find(d => d.day === activeDay.value)
  if (!dp) return
  dp.attractions.push({ ...newAttraction.value } as Attraction)
  showAddAttr.value = false
  ElMessage.success('已添加景点')
}

// ── Hotel actions ────────────────────────────────────

const hotelAmenitiesStr = ref('')

function openEditHotel(day: number) {
  const dp = dayPlans.value.find(d => d.day === day)
  if (!dp) return
  if (dp.hotel) {
    editHotel.value = { ...dp.hotel }
    hotelAmenitiesStr.value = (dp.hotel.amenities || []).join(', ')
  } else {
    editHotel.value = {
      id: 'hotel_' + Date.now(),
      name: '',
      area: '',
      price_per_night_cny: 0,
      rating: 4.0,
      location: { lat: 0, lng: 0 },
      amenities: [] as string[],
      description: '',
      booking_url: '',
    }
    hotelAmenitiesStr.value = ''
  }
  showEditHotel.value = true
  activeDay.value = day
}

function confirmEditHotel() {
  if (!editHotel.value.name?.trim()) {
    ElMessage.warning('请输入酒店名称')
    return
  }
  const dp = dayPlans.value.find(d => d.day === activeDay.value)
  if (!dp) return
  const hotel = { ...editHotel.value } as Hotel
  hotel.amenities = hotelAmenitiesStr.value
    .split(/[,，]/)
    .map(s => s.trim())
    .filter(Boolean)
  dp.hotel = hotel
  showEditHotel.value = false
  ElMessage.success('已更新酒店')
}

function removeHotel(day: number) {
  const dp = dayPlans.value.find(d => d.day === day)
  if (!dp) return
  dp.hotel = null
}

// ── Restaurant actions ───────────────────────────────

function openEditMeal(day: number, type: 'lunch' | 'dinner') {
  const dp = dayPlans.value.find(d => d.day === day)
  if (!dp) return
  const existing = type === 'lunch' ? dp.lunch : dp.dinner
  editMeal.value = existing
    ? { ...existing }
    : {
        id: 'rest_' + Date.now(),
        name: '',
        cuisine: '',
        area: '',
        avg_price_per_person_cny: 0,
        rating: 4.0,
        location: { lat: 0, lng: 0 },
        must_try_dishes: [] as string[],
        description: '',
      }
  editMealType.value = type
  editMealDay.value = day
  showEditMeal.value = true
}

function confirmEditMeal() {
  if (!editMeal.value.name?.trim()) {
    ElMessage.warning('请输入餐厅名称')
    return
  }
  const dp = dayPlans.value.find(d => d.day === editMealDay.value)
  if (!dp) return
  if (editMealType.value === 'lunch') {
    dp.lunch = { ...editMeal.value } as Restaurant
  } else {
    dp.dinner = { ...editMeal.value } as Restaurant
  }
  showEditMeal.value = false
  ElMessage.success('已更新餐厅')
}

function removeMeal(day: number, type: 'lunch' | 'dinner') {
  const dp = dayPlans.value.find(d => d.day === day)
  if (!dp) return
  if (type === 'lunch') dp.lunch = null
  else dp.dinner = null
}

// ── Save ─────────────────────────────────────────────

async function saveChanges() {
  if (!itinerary.value) return
  const updatedItinerary = {
    ...itinerary.value,
    day_plans: dayPlans.value,
    total_budget_estimate_cny: budgetItems.value.total,
  }

  saving.value = true
  try {
    const data = await updateTrip(tripId, updatedItinerary)
    ElMessage.success(`保存成功 (v${data.version})`)
    itinerary.value = data.itinerary
  } catch (e: any) {
    ElMessage.error('保存失败: ' + (e.message || '未知错误'))
  } finally {
    saving.value = false
  }
}

async function goBack() {
  const dirty = JSON.stringify(dayPlans.value) !== JSON.stringify(itinerary.value?.day_plans)
  if (dirty) {
    try {
      await ElMessageBox.confirm('有未保存的修改，确定离开吗？', '提示', {
        confirmButtonText: '离开',
        cancelButtonText: '留下',
        type: 'warning',
      })
    } catch {
      return
    }
  }
  router.push(`/trip/${tripId}`)
}
</script>

<template>
  <div class="edit-page">
    <!-- Header -->
    <div class="edit-header">
      <div class="header-left">
        <el-button text @click="goBack">← 返回详情</el-button>
        <h1>编辑行程</h1>
        <span class="header-sub">{{ itinerary?.title }}</span>
      </div>
      <div class="header-actions">
        <div class="budget-summary">
          <span class="budget-label">预估总费用</span>
          <span class="budget-value">{{ formatPrice(budgetItems.total) }}</span>
        </div>
        <el-button type="primary" :loading="saving" @click="saveChanges">
          保存修改
        </el-button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading-state">
      <el-icon class="is-loading" :size="28">
        <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="3" stroke-dasharray="31.4 31.4" stroke-linecap="round"/></svg>
      </el-icon>
      <p>加载中...</p>
    </div>

    <template v-else-if="dayPlans.length > 0">
      <!-- Budget bar -->
      <div class="budget-bar">
        <div class="budget-item">
          <span class="budget-item-label">景点门票</span>
          <span class="budget-item-value">{{ formatPrice(budgetItems.tickets) }}</span>
        </div>
        <div class="budget-item">
          <span class="budget-item-label">住宿</span>
          <span class="budget-item-value">{{ formatPrice(budgetItems.hotels) }}</span>
        </div>
        <div class="budget-item">
          <span class="budget-item-label">餐饮</span>
          <span class="budget-item-value">{{ formatPrice(budgetItems.meals) }}</span>
        </div>
        <div class="budget-item">
          <span class="budget-item-label">交通</span>
          <span class="budget-item-value">{{ formatPrice(budgetItems.transport) }}</span>
        </div>
        <div v-if="otherBudget > 0.005" class="budget-item">
          <span class="budget-item-label">其他预估费用</span>
          <span class="budget-item-value">{{ formatPrice(otherBudget) }}</span>
        </div>
        <div class="budget-item budget-item-total">
          <span class="budget-item-label">合计</span>
          <span class="budget-item-value">{{ formatPrice(budgetItems.total) }}</span>
        </div>
      </div>

      <!-- Day tabs -->
      <el-tabs v-model="activeDay" class="day-tabs">
        <el-tab-pane
          v-for="dp in dayPlans"
          :key="dp.day"
          :label="`Day ${dp.day}`"
          :name="dp.day"
        >
          <div v-if="currentDay" class="day-content">
            <!-- ═══ Attractions ═══ -->
            <div class="edit-section">
              <div class="section-header">
                <h3>景点 ({{ currentDay.attractions?.length || 0 }})</h3>
                <el-button size="small" type="primary" plain @click="openAddAttraction(currentDay.day)">
                  + 添加景点
                </el-button>
              </div>

              <div
                v-if="currentDay.attractions?.length"
                class="attr-list"
                @dragover="onDragOver"
                @drop="onDrop(currentDay.day, $event)"
              >
                <div
                  v-for="(a, i) in currentDay.attractions"
                  :key="a.id || a.name"
                  class="attr-edit-card"
                  :class="{ 'drag-over': dragDay === currentDay.day && dragIndex === i }"
                  draggable="true"
                  @dragstart="onDragStart(currentDay.day, i, $event)"
                  @dragend="onDragEnd"
                >
                  <div class="drag-handle">
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="#c0c4cc">
                      <circle cx="9" cy="5" r="2"/><circle cx="15" cy="5" r="2"/>
                      <circle cx="9" cy="12" r="2"/><circle cx="15" cy="12" r="2"/>
                      <circle cx="9" cy="19" r="2"/><circle cx="15" cy="19" r="2"/>
                    </svg>
                  </div>
                  <div class="attr-body">
                    <div class="attr-top">
                      <span class="attr-name">{{ a.name }}</span>
                      <el-tag size="small" :type="a.category === 'natural' ? 'success' : a.category === 'entertainment' ? 'warning' : ''">
                        {{ categoryTag(a.category) }}
                      </el-tag>
                    </div>
                    <div class="attr-info">
                      <span>{{ a.visit_duration_hours }}h</span>
                      <span>评分 {{ a.rating }}</span>
                      <span>{{ formatPrice(a.ticket_price_cny) }}</span>
                    </div>
                  </div>
                  <el-button
                    class="attr-delete"
                    type="danger"
                    size="small"
                    :icon="'Close'"
                    circle
                    @click="removeAttraction(currentDay.day, i)"
                  />
                </div>
              </div>
              <div v-else class="empty-hint">暂无景点，点击上方按钮添加</div>
            </div>

            <!-- ═══ Hotel ═══ -->
            <div class="edit-section">
              <div class="section-header">
                <h3>住宿</h3>
                <el-button size="small" plain @click="openEditHotel(currentDay.day)">
                  {{ currentDay.hotel ? '更换酒店' : '+ 添加酒店' }}
                </el-button>
              </div>
              <div v-if="currentDay.hotel" class="item-card hotel-card">
                <div class="item-info">
                  <div class="item-name">{{ currentDay.hotel.name }}</div>
                  <div class="item-meta">
                    <span>{{ currentDay.hotel.area }}</span>
                    <span>{{ formatPrice(currentDay.hotel.price_per_night_cny) }}/晚</span>
                    <span>评分 {{ currentDay.hotel.rating }}</span>
                  </div>
                </div>
                <el-button type="danger" link size="small" @click="removeHotel(currentDay.day)">移除</el-button>
              </div>
              <div v-else class="empty-hint">未安排住宿</div>
            </div>

            <!-- ═══ Meals ═══ -->
            <div class="edit-section">
              <div class="section-header"><h3>餐饮</h3></div>
              <div class="meal-row">
                <div class="meal-slot">
                  <div class="meal-label">午餐</div>
                  <div v-if="currentDay.lunch" class="item-card meal-card">
                    <div class="item-info">
                      <div class="item-name">{{ currentDay.lunch.name }}</div>
                      <div class="item-meta">
                        <span>{{ currentDay.lunch.cuisine }}</span>
                        <span>{{ formatPrice(currentDay.lunch.avg_price_per_person_cny) }}/人</span>
                      </div>
                    </div>
                    <div class="meal-actions">
                      <el-button size="small" plain @click="openEditMeal(currentDay.day, 'lunch')">更换</el-button>
                      <el-button size="small" type="danger" link @click="removeMeal(currentDay.day, 'lunch')">移除</el-button>
                    </div>
                  </div>
                  <div v-else class="empty-hint">
                    未安排
                    <el-button size="small" type="primary" link @click="openEditMeal(currentDay.day, 'lunch')">添加</el-button>
                  </div>
                </div>
                <div class="meal-slot">
                  <div class="meal-label">晚餐</div>
                  <div v-if="currentDay.dinner" class="item-card meal-card">
                    <div class="item-info">
                      <div class="item-name">{{ currentDay.dinner.name }}</div>
                      <div class="item-meta">
                        <span>{{ currentDay.dinner.cuisine }}</span>
                        <span>{{ formatPrice(currentDay.dinner.avg_price_per_person_cny) }}/人</span>
                      </div>
                    </div>
                    <div class="meal-actions">
                      <el-button size="small" plain @click="openEditMeal(currentDay.day, 'dinner')">更换</el-button>
                      <el-button size="small" type="danger" link @click="removeMeal(currentDay.day, 'dinner')">移除</el-button>
                    </div>
                  </div>
                  <div v-else class="empty-hint">
                    未安排
                    <el-button size="small" type="primary" link @click="openEditMeal(currentDay.day, 'dinner')">添加</el-button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </template>

    <!-- Empty state -->
    <div v-else-if="!loading" class="empty-state">
      <el-empty description="未找到行程数据" />
    </div>

    <!-- ═══ Add Attraction Dialog ═══ -->
    <el-dialog v-model="showAddAttr" title="添加景点" width="500px" destroy-on-close>
      <el-form label-position="top" size="default">
        <el-form-item label="景点名称" required>
          <el-input v-model="newAttraction.name" placeholder="例如：杜甫草堂" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="分类">
              <el-select v-model="newAttraction.category" style="width:100%">
                <el-option label="文化" value="cultural" />
                <el-option label="自然" value="natural" />
                <el-option label="娱乐" value="entertainment" />
                <el-option label="购物" value="shopping" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="评分">
              <el-input-number v-model="newAttraction.rating" :min="0" :max="5" :step="0.1" :precision="1" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="游玩时长(小时)">
              <el-input-number v-model="newAttraction.visit_duration_hours" :min="0.5" :max="12" :step="0.5" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="门票(元)">
              <el-input-number v-model="newAttraction.ticket_price_cny" :min="0" :step="10" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="简介">
          <el-input v-model="newAttraction.description" type="textarea" :rows="2" placeholder="简短描述..." />
        </el-form-item>
        <el-form-item label="营业时间">
          <el-input v-model="newAttraction.opening_hours" placeholder="例如：08:00-18:00" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddAttr = false">取消</el-button>
        <el-button type="primary" @click="confirmAddAttraction">添加</el-button>
      </template>
    </el-dialog>

    <!-- ═══ Edit Hotel Dialog ═══ -->
    <el-dialog v-model="showEditHotel" title="编辑酒店" width="500px" destroy-on-close>
      <el-form label-position="top" size="default">
        <el-form-item label="酒店名称" required>
          <el-input v-model="editHotel.name" placeholder="例如：成都锦江宾馆" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="区域">
              <el-input v-model="editHotel.area" placeholder="例如：春熙路" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="评分">
              <el-input-number v-model="editHotel.rating" :min="0" :max="5" :step="0.1" :precision="1" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="每晚价格(元)">
          <el-input-number v-model="editHotel.price_per_night_cny" :min="0" :step="50" style="width:100%" />
        </el-form-item>
        <el-form-item label="设施（逗号分隔）">
          <el-input v-model="hotelAmenitiesStr" placeholder="WiFi, 停车场, 健身房" />
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="editHotel.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditHotel = false">取消</el-button>
        <el-button type="primary" @click="confirmEditHotel">确认</el-button>
      </template>
    </el-dialog>

    <!-- ═══ Edit Restaurant Dialog ═══ -->
    <el-dialog v-model="showEditMeal" title="编辑餐厅" width="500px" destroy-on-close>
      <el-form label-position="top" size="default">
        <el-form-item label="餐厅名称" required>
          <el-input v-model="editMeal.name" placeholder="例如：小龙坎火锅" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="菜系">
              <el-input v-model="editMeal.cuisine" placeholder="例如：川菜" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="区域">
              <el-input v-model="editMeal.area" placeholder="例如：春熙路" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="人均消费(元)">
              <el-input-number v-model="editMeal.avg_price_per_person_cny" :min="0" :step="10" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="评分">
              <el-input-number v-model="editMeal.rating" :min="0" :max="5" :step="0.1" :precision="1" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="简介">
          <el-input v-model="editMeal.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditMeal = false">取消</el-button>
        <el-button type="primary" @click="confirmEditMeal">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.edit-page { max-width: 1000px; margin: 0 auto; padding: 20px 16px 40px; }

/* Header */
.edit-header {
  display: flex; justify-content: space-between; align-items: flex-start;
  background: #fff; border-radius: 12px; padding: 20px 24px; margin-bottom: 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06);
}
.header-left h1 { font-size: 22px; margin: 4px 0 0; }
.header-sub { font-size: 13px; color: #909399; }
.header-actions { display: flex; align-items: center; gap: 16px; }
.budget-summary { text-align: right; }
.budget-label { display: block; font-size: 12px; color: #909399; }
.budget-value { font-size: 24px; font-weight: 700; color: #67c23a; }

/* Budget bar */
.budget-bar {
  display: flex; gap: 0; background: #fff; border-radius: 12px; padding: 12px 20px;
  margin-bottom: 16px; box-shadow: 0 1px 4px rgba(0,0,0,.06);
}
.budget-item { flex: 1; text-align: center; border-right: 1px solid #ebeef5; }
.budget-item:last-child { border-right: none; }
.budget-item-label { display: block; font-size: 12px; color: #909399; margin-bottom: 4px; }
.budget-item-value { font-size: 16px; font-weight: 600; color: #303133; }
.budget-item-total .budget-item-value { color: #67c23a; }

/* Loading */
.loading-state { display: flex; flex-direction: column; align-items: center; padding: 80px; color: #909399; }

/* Day tabs */
.day-tabs { background: #fff; border-radius: 12px; padding: 16px 20px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.day-content { min-height: 300px; }

/* Sections */
.edit-section { margin-bottom: 24px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.section-header h3 { font-size: 15px; color: #303133; margin: 0; }

/* Attraction edit cards */
.attr-edit-card {
  display: flex; align-items: center; gap: 10px;
  background: #f5f7fa; border-radius: 8px; padding: 10px 12px; margin-bottom: 8px;
  border: 2px solid transparent; transition: border-color .2s, background .2s;
}
.attr-edit-card.drag-over { border-color: #409eff; background: #ecf5ff; }
.drag-handle { cursor: grab; flex-shrink: 0; display: flex; align-items: center; }
.drag-handle:active { cursor: grabbing; }
.attr-body { flex: 1; min-width: 0; }
.attr-top { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.attr-name { font-weight: 600; font-size: 14px; }
.attr-info { display: flex; gap: 12px; font-size: 12px; color: #909399; }
.attr-delete { flex-shrink: 0; }

/* Item cards (hotel/meal) */
.item-card {
  display: flex; justify-content: space-between; align-items: center;
  border-radius: 8px; padding: 12px;
}
.item-info { flex: 1; }
.item-name { font-weight: 600; font-size: 14px; color: #303133; }
.item-meta { display: flex; gap: 12px; font-size: 12px; color: #909399; margin-top: 4px; }
.hotel-card { background: #ecf5ff; }
.meal-card { background: #fdf6ec; }

/* Meal row */
.meal-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.meal-slot { }
.meal-label { font-size: 13px; font-weight: 600; color: #606266; margin-bottom: 8px; }
.meal-actions { display: flex; gap: 4px; align-items: center; flex-shrink: 0; }

/* Empty */
.empty-hint { font-size: 13px; color: #c0c4cc; padding: 8px 0; }
.empty-state { display: flex; justify-content: center; padding: 80px 0; }

/* Override Element Plus tab header */
:deep(.el-tabs__header) { margin-bottom: 20px; }
</style>

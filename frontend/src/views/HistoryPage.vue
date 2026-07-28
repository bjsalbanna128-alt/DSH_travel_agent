<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { listTrips } from '../api/travel'

const router = useRouter()
const trips = ref<any[]>([])
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    trips.value = await listTrips()
  } catch (e: any) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
})

function viewTrip(tripId: string) {
  router.push(`/trip/${tripId}`)
}

function formatDate(iso: string) {
  return iso ? iso.slice(0, 10) : ''
}
</script>

<template>
  <div class="history-page">
    <div class="history-header">
      <h2>历史行程</h2>
      <el-button type="primary" @click="router.push('/')">新建规划</el-button>
    </div>

    <div v-if="loading" class="loading-state">
      <el-icon class="is-loading"><svg /></el-icon>
      <span>加载中...</span>
    </div>

    <div v-else-if="error" class="error-state">
      <p>{{ error }}</p>
    </div>

    <div v-else-if="trips.length === 0" class="empty-state">
      <el-empty description="暂无历史行程">
        <el-button type="primary" @click="router.push('/')">开始规划</el-button>
      </el-empty>
    </div>

    <div v-else class="trip-list">
      <div
        v-for="trip in trips"
        :key="trip.id"
        class="trip-card"
        @click="viewTrip(trip.id)"
      >
        <div class="card-left">
          <h3>{{ trip.title || '未命名行程' }}</h3>
          <div class="card-meta">
            <el-tag size="small">{{ trip.destination }}</el-tag>
            <span>{{ trip.duration_days }} 天</span>
            <span v-if="trip.budget_total">¥{{ trip.budget_total.toLocaleString() }}</span>
            <span class="card-date">{{ formatDate(trip.created_at) }}</span>
          </div>
        </div>
        <div class="card-right">
          <el-button text>查看详情 →</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.history-page { max-width: 800px; margin: 0 auto; padding: 24px 16px; }
.history-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.history-header h2 { margin: 0; font-size: 22px; }

.loading-state, .error-state, .empty-state { text-align: center; padding: 60px 0; color: #909399; }

.trip-list { display: flex; flex-direction: column; gap: 12px; }
.trip-card {
  display: flex; justify-content: space-between; align-items: center;
  background: #fff; border-radius: 10px; padding: 18px 20px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06); cursor: pointer;
  transition: box-shadow .2s;
}
.trip-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,.1); }
.card-left h3 { margin: 0 0 8px; font-size: 16px; }
.card-meta { display: flex; gap: 12px; align-items: center; font-size: 13px; color: #606266; }
.card-date { color: #909399; }
</style>

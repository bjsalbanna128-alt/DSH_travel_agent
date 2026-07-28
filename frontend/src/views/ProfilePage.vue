<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PreferenceCard from '../components/PreferenceCard.vue'
import { getProfile, listTrips } from '../api/travel'
import { useAuthStore } from '../stores/auth'
import type { UserProfile } from '../types/profile'

const router = useRouter()
const auth = useAuthStore()

const profile = ref<UserProfile | null>(null)
const trips = ref<any[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    const [profileData, tripData] = await Promise.all([
      getProfile(),
      listTrips(),
    ])
    profile.value = profileData.profile
    trips.value = tripData.slice(0, 10)
  } catch (e: any) {
    console.error('Failed to load profile:', e)
  } finally {
    loading.value = false
  }
})

function goToTrip(tripId: string) {
  router.push(`/trip/${tripId}`)
}
</script>

<template>
  <div class="profile-page">
    <div class="page-header">
      <el-button text @click="router.push('/')">← 首页</el-button>
      <h1>{{ auth.username || '我的' }}</h1>
      <el-button v-if="auth.isLoggedIn" text type="danger" size="small" @click="auth.logout(); router.push('/')">退出登录</el-button>
      <div v-else />
    </div>

    <div v-if="!auth.isLoggedIn" style="text-align:center;padding:40px">
      <p style="color:#909399;margin-bottom:16px">登录后可查看个性化偏好和历史行程</p>
      <el-button type="primary" @click="router.push('/login')">去登录</el-button>
    </div>

    <div v-else-if="loading" class="loading-state">
      <el-icon class="is-loading" :size="24">
        <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="3" stroke-dasharray="31.4 31.4" stroke-linecap="round"/></svg>
      </el-icon>
      <p>加载中...</p>
    </div>

    <template v-else>
      <el-row :gutter="24">
        <el-col :span="12">
          <PreferenceCard :profile="profile" />
        </el-col>

        <el-col :span="12">
          <div class="history-card">
            <h3>最近行程</h3>
            <div v-if="trips.length === 0" class="empty-hint">
              <p>还没有旅行记录</p>
              <el-button type="primary" @click="router.push('/')">去规划一个旅行</el-button>
            </div>
            <div v-else class="trip-list">
              <div
                v-for="trip in trips"
                :key="trip.id"
                class="trip-item"
                @click="goToTrip(trip.id)"
              >
                <div class="trip-title">{{ trip.title || '未命名行程' }}</div>
                <div class="trip-meta">
                  <el-tag size="small">{{ trip.destination }}</el-tag>
                  <span>{{ trip.duration_days }}天</span>
                  <span v-if="trip.budget_total > 0">¥{{ trip.budget_total.toLocaleString() }}</span>
                  <span>{{ trip.created_at?.slice(0, 10) }}</span>
                </div>
              </div>
            </div>
          </div>
        </el-col>
      </el-row>
    </template>
  </div>
</template>

<style scoped>
.profile-page { max-width: 1000px; margin: 0 auto; padding: 20px 16px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.page-header h1 { font-size: 22px; margin: 0; }

.loading-state { display: flex; flex-direction: column; align-items: center; padding: 60px; color: #909399; }

.history-card { background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.history-card h3 { font-size: 16px; margin: 0 0 16px; }

.empty-hint { text-align: center; padding: 40px; color: #909399; }

.trip-list { display: flex; flex-direction: column; gap: 8px; }
.trip-item { padding: 12px; border-radius: 8px; background: #f5f7fa; cursor: pointer; transition: background .2s; }
.trip-item:hover { background: #ecf5ff; }
.trip-title { font-weight: 600; font-size: 14px; color: #303133; margin-bottom: 6px; }
.trip-meta { display: flex; gap: 8px; align-items: center; font-size: 12px; color: #909399; }
</style>

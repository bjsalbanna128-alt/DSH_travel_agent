<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { adminError } from '../api/adminResources'
import { adminTripsApi } from '../api/adminTrips'
import DayPlanList from '../components/DayPlanList.vue'
import { useAdminQuery } from '../composables/useAdminQuery'
import { confirmedLabel, tripTime, type TripVersionDetail } from '../types/adminTrips'

const route = useRoute()
const tripId = computed(() => String(route.params.id))
const { data, loading, error, load, clear } = useAdminQuery(signal =>
  adminTripsApi.trip(tripId.value, signal))

const versionOpen = ref(false)
const versionLoading = ref(false)
const versionError = ref('')
const versionDetail = ref<TripVersionDetail>()
let versionRequest: AbortController | undefined

watch(tripId, () => {
  clear()
  versionOpen.value = false
  versionDetail.value = undefined
  void load()
}, { immediate: true })

async function openVersion(version: number) {
  versionRequest?.abort()
  const request = new AbortController()
  versionRequest = request
  versionOpen.value = true
  versionDetail.value = undefined
  versionError.value = ''
  versionLoading.value = true
  try {
    const detail = await adminTripsApi.version(tripId.value, version, request.signal)
    if (!request.signal.aborted) versionDetail.value = detail
  } catch (failure) {
    if (!request.signal.aborted) versionError.value = adminError(failure)
  } finally {
    if (!request.signal.aborted) versionLoading.value = false
  }
}

const plan = computed(() => versionDetail.value?.itinerary ?? data.value?.itinerary)
</script>

<template>
  <section class="resource-page support-page">
    <header class="resource-titlebar">
      <h1>{{ data?.title || '行程详情' }}</h1>
      <router-link class="resource-link" :to="{ name: 'admin-trips' }">返回行程查询</router-link>
    </header>

    <div v-if="error" class="resource-panel resource-stack">
      <el-alert :title="error" type="error" :closable="false" show-icon />
      <div><el-button :loading="loading" @click="load">重试</el-button></div>
    </div>
    <p v-else-if="loading && !data" role="status">正在加载行程…</p>

    <template v-else-if="data">
      <section class="resource-panel">
        <dl class="resource-grid">
          <div><dt>行程号</dt><dd>{{ data.id }}</dd></div>
          <div><dt>游客账号</dt><dd>{{ data.username }}</dd></div>
          <div><dt>目的地</dt><dd>{{ data.destination || '—' }}</dd></div>
          <div><dt>天数</dt><dd>{{ data.duration_days }} 天</dd></div>
          <div><dt>预估总费用</dt><dd>{{ data.budget_total > 0 ? `¥${data.budget_total.toLocaleString()}` : '—' }}</dd></div>
          <div><dt>当前版本</dt><dd>v{{ data.version }}</dd></div>
          <div>
            <dt>确认版本</dt>
            <dd>
              {{ confirmedLabel(data.confirmed_version) }}
              <router-link :to="{ name: 'admin-ai-quality', query: { trip: data.id, version: data.confirmed_version ?? data.version } }">查看质检</router-link>
            </dd>
          </div>
          <div><dt>创建时间（北京时间）</dt><dd>{{ tripTime(data.created_at) }}</dd></div>
          <div><dt>最近更新（北京时间）</dt><dd>{{ tripTime(data.updated_at) }}</dd></div>
        </dl>
      </section>

      <section class="resource-panel resource-stack">
        <h2>当前行程</h2>
        <DayPlanList
          v-if="data.itinerary?.day_plans?.length"
          :day-plans="data.itinerary.day_plans"
          :total-budget="data.itinerary.total_budget_estimate_cny ?? 0"
        />
        <p v-else class="resource-muted">该行程没有日程数据。</p>
      </section>

      <section class="resource-panel resource-stack">
        <h2>历史版本</h2>
        <el-table :data="data.versions" row-key="version" empty-text="没有版本记录">
          <el-table-column label="版本" width="90">
            <template #default="{ row }">v{{ row.version }}</template>
          </el-table-column>
          <el-table-column prop="description" label="说明" min-width="180" />
          <el-table-column label="时间（北京时间）" min-width="170">
            <template #default="{ row }">{{ tripTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="标记" min-width="170">
            <template #default="{ row }">
              <el-tag v-if="row.is_current" size="small" type="success" effect="plain">当前版本</el-tag>
              <el-tag v-if="row.is_confirmed" size="small" type="warning" effect="plain" style="margin-left:6px">确认版本</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="110">
            <template #default="{ row }">
              <el-button text size="small" @click="openVersion(row.version)">查看内容</el-button>
            </template>
          </el-table-column>
        </el-table>
        <p class="resource-muted">运营只能查看，不能修改或回滚行程。</p>
      </section>
    </template>

    <el-dialog v-model="versionOpen" :title="versionDetail ? `版本 v${versionDetail.version}` : '版本内容'" width="720px">
      <div v-if="versionError" class="resource-stack">
        <el-alert :title="versionError" type="error" :closable="false" show-icon />
      </div>
      <p v-else-if="versionLoading" role="status">正在加载版本内容…</p>
      <template v-else-if="versionDetail">
        <p class="resource-muted">
          {{ versionDetail.description || '无说明' }} · {{ tripTime(versionDetail.created_at) }}
          <el-tag v-if="versionDetail.is_confirmed" size="small" type="warning" effect="plain" style="margin-left:6px">确认版本</el-tag>
        </p>
        <DayPlanList
          v-if="plan?.day_plans?.length"
          :day-plans="plan.day_plans"
          :total-budget="plan.total_budget_estimate_cny ?? 0"
        />
        <p v-else class="resource-muted">该版本没有日程数据。</p>
      </template>
    </el-dialog>
  </section>
</template>

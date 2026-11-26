<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { adminQueryString } from '../api/adminResources'
import { aiOperation } from '../api/aiOperations'
import { useAdminQuery } from '../composables/useAdminQuery'
import type { PageResult } from '../types/adminResources'
import { qualityRules, qualityStages, qualityStatuses, type QualitySummary, type QualityDetail } from '../types/scenicQuality'

const base = '/quality-reports'
const page = ref(1)
const filters = reactive({ status: '', rule: '' })
const route = useRoute()
const router = useRouter()
const drawerOpen = ref(false)
const matchingRules = { id: '来源与 POI ID', unique_name: '同城唯一名称', ambiguous: '景区身份待确认' }
const reportStatuses = Object.entries(qualityStatuses).filter(([value]) => value !== 'unchecked')
const { data, loading, error, load } = useAdminQuery(() => aiOperation<PageResult<QualitySummary>>(
  `${base}${adminQueryString({ ...filters, page: page.value })}`,
))
const detail = useAdminQuery(() => aiOperation<QualityDetail>(
  `${base}/${encodeURIComponent(String(route.query.trip))}/${encodeURIComponent(String(route.query.version))}`,
))
const dateTime = new Intl.DateTimeFormat('zh-CN', { dateStyle: 'short', timeStyle: 'medium', timeZone: 'Asia/Shanghai' })
function search() { page.value = 1; void load() }
function openReport(row: QualitySummary) {
  void router.replace({ query: { trip: row.trip_id, version: row.version } })
}
function closeReport() {
  if (route.query.trip) void router.replace({ query: {} })
}
watch([() => route.query.trip, () => route.query.version], ([trip, version]) => {
  detail.clear()
  drawerOpen.value = typeof trip === 'string' && typeof version === 'string' && /^\d+$/.test(version)
  if (drawerOpen.value) void detail.load()
}, { immediate: true })
onMounted(load)
</script>

<template>
  <section class="resource-page">
    <header class="resource-titlebar"><h1>规划质检</h1></header>
    <el-alert v-if="error" :title="error" :closable="false" type="error" />
    <div class="resource-panel">
      <el-form class="resource-toolbar" @submit.prevent="search">
        <el-select v-model="filters.status" aria-label="按结果筛选" placeholder="全部结果" clearable value-on-clear="">
          <el-option v-for="[value, label] in reportStatuses" :key="value" :label="label" :value="value" />
        </el-select>
        <el-select v-model="filters.rule" aria-label="按质检规则筛选" placeholder="全部规则" clearable value-on-clear="">
          <el-option v-for="(label, value) in qualityRules" :key="value" :label="label" :value="value" />
        </el-select>
        <el-button native-type="submit">查询</el-button>
      </el-form>
      <el-table v-loading="loading" :data="data?.items ?? []" empty-text="暂无质检报告">
        <el-table-column prop="trip_id" label="行程标识" min-width="235" />
        <el-table-column prop="destination" label="目的地" min-width="104" />
        <el-table-column label="版本" min-width="110">
          <template #default="{ row }: { row: QualitySummary }">{{ row.stage ? qualityStages[row.stage] : '' }} v{{ row.version }}</template>
        </el-table-column>
        <el-table-column label="检查时间（北京时间）" min-width="165">
          <template #default="{ row }: { row: QualitySummary }">{{ row.checked_at ? dateTime.format(new Date(row.checked_at)) : '—' }}</template>
        </el-table-column>
        <el-table-column label="结果" width="100">
          <template #default="{ row }: { row: QualitySummary }">{{ qualityStatuses[row.status] }}</template>
        </el-table-column>
        <el-table-column label="操作" width="96">
          <template #default="{ row }"><el-button link type="primary" @click="openReport(row)">查看报告</el-button></template>
        </el-table-column>
      </el-table>
      <el-pagination v-model:current-page="page" :total="data?.total ?? 0" :page-size="20" layout="prev, pager, next, total" @current-change="load" />
    </div>
    <el-drawer v-model="drawerOpen" title="质检报告" size="min(760px, 96vw)" @close="closeReport">
      <div v-loading="detail.loading.value">
        <el-alert v-if="detail.error.value" :title="detail.error.value" :closable="false" type="error" />
        <template v-if="detail.data.value">
          <h2>{{ detail.data.value.destination }} · v{{ detail.data.value.version }} · {{ qualityStatuses[detail.data.value.status] }}</h2>
          <p>行程 {{ detail.data.value.trip_id }}</p>
          <p v-if="detail.data.value.status === 'unchecked'">该版本没有质检记录。</p>
          <p v-else-if="!detail.data.value.findings.length">本次质检未发现问题。</p>
          <article v-for="(item, index) in detail.data.value.findings" :key="index" class="quality-finding">
            <h3>{{ qualityRules[item.rule] }} · {{ qualityStatuses[item.result] }}</h3>
            <p v-if="item.day || item.attraction">
              <span v-if="item.day">第 {{ item.day }} 天 · {{ item.visit_date || '日期未明确' }} </span>
              <span v-if="item.attraction">· {{ item.attraction }}</span>
            </p>
            <p>{{ item.reason }}</p>
            <template v-if="item.restriction_id">
              <p>{{ item.description }} · 来源 {{ item.source_note }}</p>
              <p>条目 {{ item.restriction_id }} v{{ item.restriction_version }} · {{ item.matched_by && matchingRules[item.matched_by] }}</p>
            </template>
          </article>
        </template>
      </div>
    </el-drawer>
  </section>
</template>

<style scoped>
.quality-finding { padding: 12px 16px; margin-block: 12px; border: 1px solid #e1e7f0; border-radius: 8px; overflow-wrap: anywhere; }
.quality-finding p { margin: 6px 0; }
.el-pagination { margin-top: 12px; }
</style>

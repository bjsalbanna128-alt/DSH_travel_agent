<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { adminTripsApi } from '../api/adminTrips'
import { useAdminQuery } from '../composables/useAdminQuery'
import { confirmedLabel, tripTime } from '../types/adminTrips'

const page = ref(1)
const filters = reactive({ username: '', destination: '', start: '', end: '' })
const { data, loading, error, load } = useAdminQuery(signal =>
  adminTripsApi.trips({ ...filters, page: page.value }, signal))
onMounted(load)

function search() {
  page.value = 1
  void load()
}
</script>

<template>
  <section class="resource-page support-page">
    <header class="resource-titlebar"><h1>行程查询</h1></header>
    <section class="resource-panel">
      <form class="resource-toolbar" @submit.prevent="search">
        <el-input v-model="filters.username" placeholder="游客用户名" aria-label="按用户名筛选" maxlength="50" clearable />
        <el-input v-model="filters.destination" placeholder="目的地" aria-label="按目的地筛选" maxlength="100" clearable />
        <el-input v-model="filters.start" type="date" aria-label="更新开始日期" />
        <el-input v-model="filters.end" type="date" aria-label="更新结束日期" />
        <el-button native-type="submit" :loading="loading">查询行程</el-button>
      </form>
      <div v-if="error" class="support-error resource-stack">
        <el-alert :title="error" type="error" :closable="false" show-icon />
        <div><el-button @click="load">重试</el-button></div>
      </div>
      <el-table v-if="data || !error" v-loading="loading" :data="data?.items ?? []" row-key="id"
        empty-text="没有符合条件的已确认行程">
        <el-table-column label="行程" min-width="220">
          <template #default="{ row }">
            <router-link class="resource-link" :to="{ name: 'admin-trip-detail', params: { id: row.id } }">
              {{ row.title || '未命名行程' }}
            </router-link>
            <div class="resource-muted">{{ row.id }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="username" label="游客账号" min-width="130" />
        <el-table-column prop="destination" label="目的地" min-width="100" />
        <el-table-column label="天数" width="80">
          <template #default="{ row }">{{ row.duration_days }} 天</template>
        </el-table-column>
        <el-table-column label="版本" min-width="150">
          <template #default="{ row }">
            当前 v{{ row.version }}
            <div class="resource-muted">确认 {{ confirmedLabel(row.confirmed_version) }}</div>
          </template>
        </el-table-column>
        <el-table-column label="预估总费用" min-width="120">
          <template #default="{ row }">{{ row.budget_total > 0 ? `¥${row.budget_total.toLocaleString()}` : '—' }}</template>
        </el-table-column>
        <el-table-column label="最近更新（北京时间）" min-width="170">
          <template #default="{ row }">{{ tripTime(row.updated_at) }}</template>
        </el-table-column>
      </el-table>
      <div v-if="data && data.total > 20" class="resource-pagination">
        <el-pagination v-model:current-page="page" :page-size="20" :total="data.total"
          layout="total, prev, pager, next" @current-change="load" />
      </div>
    </section>
  </section>
</template>

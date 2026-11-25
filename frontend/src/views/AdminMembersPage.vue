<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { membershipApi } from '../api/membership'
import { useAdminQuery } from '../composables/useAdminQuery'
import { memberTime } from '../types/membership'

const page = ref(1)
const filters = reactive({ username: '', start: '', end: '' })
const { data, loading, error, load } = useAdminQuery(signal =>
  membershipApi.members({ ...filters, page: page.value }, signal))
onMounted(load)

function search() {
  page.value = 1
  void load()
}
</script>

<template>
  <section class="resource-page support-page">
    <header class="resource-titlebar"><h1>用户会员</h1></header>
    <section class="resource-panel">
      <form class="resource-toolbar" @submit.prevent="search">
        <el-input v-model="filters.username" placeholder="游客用户名" aria-label="按用户名筛选" maxlength="50" clearable />
        <el-input v-model="filters.start" type="date" aria-label="注册开始日期" />
        <el-input v-model="filters.end" type="date" aria-label="注册结束日期" />
        <el-button native-type="submit" :loading="loading">查询会员</el-button>
      </form>
      <div v-if="error" class="support-error resource-stack">
        <el-alert :title="error" type="error" :closable="false" show-icon />
        <div><el-button @click="load">重试</el-button></div>
      </div>
      <el-table v-if="data || !error" v-loading="loading" :data="data?.items ?? []" row-key="id" empty-text="没有符合条件的游客">
        <el-table-column label="游客账号" min-width="145">
          <template #default="{ row }">
            <router-link class="resource-link" :to="{ name: 'admin-member-detail', params: { id: row.id } }">{{ row.username }}</router-link>
          </template>
        </el-table-column>
        <el-table-column label="注册时间（北京时间）" min-width="170">
          <template #default="{ row }">{{ memberTime(row.registered_at) }}</template>
        </el-table-column>
        <el-table-column label="资料状态" min-width="110">
          <template #default="{ row }">{{ row.profile_complete ? '已完善' : '待完善' }}</template>
        </el-table-column>
        <el-table-column label="有效积分" min-width="100">
          <template #default="{ row }">{{ row.effective_balance.toLocaleString() }} 分</template>
        </el-table-column>
      </el-table>
      <div v-if="data && data.total > 20" class="resource-pagination">
        <el-pagination v-model:current-page="page" :page-size="20" :total="data.total"
          layout="total, prev, pager, next" @current-change="load" />
      </div>
    </section>
  </section>
</template>

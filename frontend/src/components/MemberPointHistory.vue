<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { membershipApi } from '../api/membership'
import { useAdminQuery } from '../composables/useAdminQuery'
import { memberTime, pointLabels, type PointKind } from '../types/membership'

const props = defineProps<{ memberId?: string }>()
const page = ref(1)
const filters = reactive({ order_id: '', kind: '' as PointKind | '', start: '', end: '' })
const { data, loading, error, load } = useAdminQuery(signal => props.memberId
  ? membershipApi.memberLedger(props.memberId, { ...filters, page: page.value }, signal)
  : membershipApi.myLedger({ page: page.value }, signal))
onMounted(load)

function search() {
  page.value = 1
  void load()
}
</script>

<template>
  <section class="resource-panel">
    <h2 class="support-section-title">积分流水</h2>
    <form v-if="memberId" class="resource-toolbar" @submit.prevent="search">
      <el-input v-model="filters.order_id" placeholder="来源订单号" aria-label="按订单号查账" maxlength="128" clearable />
      <el-select v-model="filters.kind" placeholder="全部变动类型" aria-label="按变动类型查账" clearable value-on-clear="">
        <el-option v-for="(label, key) in pointLabels" :key="key" :label="label" :value="key" />
      </el-select>
      <el-input v-model="filters.start" type="date" aria-label="流水开始日期" />
      <el-input v-model="filters.end" type="date" aria-label="流水结束日期" />
      <el-button native-type="submit" :loading="loading">查询流水</el-button>
    </form>
    <div v-if="error" class="support-error resource-stack">
      <el-alert :title="error" type="error" :closable="false" show-icon />
      <div><el-button @click="load">重试</el-button></div>
    </div>
    <el-table v-if="data || !error" v-loading="loading" :data="data?.items ?? []" row-key="id" empty-text="暂无积分流水">
      <el-table-column label="变动原因" min-width="105">
        <template #default="{ row }">{{ pointLabels[row.kind as PointKind] }}</template>
      </el-table-column>
      <el-table-column label="订单 / 退款单" min-width="150">
        <template #default="{ row }">
          <span>{{ row.order_id }}</span>
          <p v-if="row.refund_id" class="resource-muted">退款单 {{ row.refund_id }}</p>
        </template>
      </el-table-column>
      <el-table-column label="积分变动" width="100">
        <template #default="{ row }"><strong>{{ row.delta > 0 ? '+' : '' }}{{ row.delta.toLocaleString() }}</strong></template>
      </el-table-column>
      <el-table-column label="业务时间（北京时间）" min-width="155">
        <template #default="{ row }">{{ memberTime(row.occurred_at) }}</template>
      </el-table-column>
      <el-table-column v-if="memberId" label="记账后余额" prop="book_balance_after" width="110" />
    </el-table>
    <div v-if="data && data.total > 20" class="resource-pagination">
      <el-pagination v-model:current-page="page" :page-size="20" :total="data.total"
        layout="total, prev, pager, next" @current-change="load" />
    </div>
  </section>
</template>

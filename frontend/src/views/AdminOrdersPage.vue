<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminError } from '../api/adminResources'
import { ordersApi } from '../api/orders'
import { useAdminQuery } from '../composables/useAdminQuery'
import {
  formatFen, fundStatusLabels, orderStatusLabels, orderTime,
  type FundStatus, type OrderDetail, type OrderStatus, type OrderSummary,
} from '../types/orders'

const page = ref(1)
const filters = reactive({ status: 'paid_pending_review' as OrderStatus | '', keyword: '' })
const { data, loading, error, load } = useAdminQuery(signal =>
  ordersApi.queue({ ...filters, page: page.value, page_size: 20 }, signal))

const selected = ref<OrderDetail>()
const detailLoading = ref(false)
const actionLoading = ref(false)
const stockouts = ref<string[]>([])
const supplierReply = ref('')
const usage = ref<'unknown' | 'unused' | 'used'>('unknown')

function search() {
  page.value = 1
  void load()
}

async function openDetail(row: OrderSummary) {
  detailLoading.value = true
  selected.value = undefined
  try {
    selected.value = await ordersApi.adminDetail(row.id, new AbortController().signal)
    stockouts.value = []
    supplierReply.value = ''
    usage.value = 'unknown'
  } catch (failure) {
    ElMessage.error(adminError(failure))
  } finally {
    detailLoading.value = false
  }
}

async function approve(order: OrderDetail) {
  actionLoading.value = true
  try {
    selected.value = await ordersApi.approve(order.id, '已与供应商核实可供给')
    ElMessage.success('已通过复核，库存转为确认占用')
    await load()
  } catch (failure) {
    ElMessage.error(adminError(failure))
  } finally {
    actionLoading.value = false
  }
}

async function reject(order: OrderDetail) {
  const reason = await ElMessageBox.prompt(stockouts.value.length ? '记录缺货原因。勾选的日报价将同时停售。' : '记录其他拒绝原因。缺货时请先勾选对应日报价。', '拒绝订单', {
    inputPattern: /\S+/, inputErrorMessage: '原因不能为空',
  }).then(result => result.value, () => null)
  if (!reason) return
  actionLoading.value = true
  try {
    const items = order.items.filter(item => stockouts.value.includes(item.id))
      .map(item => ({ product_id: item.product_id, service_date: item.service_date }))
    selected.value = await ordersApi.reject(order.id, { reason, category: items.length ? 'stockout' : 'other', items })
    ElMessage.success('已拒绝并登记全额退款')
    await load()
  } catch (failure) {
    ElMessage.error(adminError(failure))
  } finally {
    actionLoading.value = false
  }
}

async function resolveCancel(order: OrderDetail, approveCancel: boolean) {
  actionLoading.value = true
  try {
    selected.value = await ordersApi.resolveCancel(
      order.id, approveCancel, supplierReply.value.trim(), usage.value,
    )
    ElMessage.success(usage.value === 'used' ? '已转售后工单' : usage.value === 'unknown' ? '已记录，继续人工核实'
      : approveCancel ? '已取消并登记退款' : '已驳回取消申请')
    await load()
  } catch (failure) {
    ElMessage.error(adminError(failure))
  } finally {
    actionLoading.value = false
  }
}

async function sweep() {
  try {
    const result = await ordersApi.sweep()
    ElMessage.success(`已关闭 ${result.expired} 笔超时单，处理 ${result.refunds} 笔待退款`)
    await load()
  } catch (failure) {
    ElMessage.error(adminError(failure))
  }
}

onMounted(load)
</script>

<template>
  <section class="resource-page">
    <header class="resource-titlebar">
      <h1>订单复核</h1>
      <div class="resource-actions">
        <el-button @click="sweep">清理超时单 · 处理退款</el-button>
      </div>
    </header>
    <div class="resource-panel">
      <form class="resource-toolbar" @submit.prevent="search">
        <el-select v-model="filters.status" placeholder="全部状态" clearable aria-label="状态筛选">
          <el-option v-for="(label, value) in orderStatusLabels" :key="value" :label="label" :value="value" />
        </el-select>
        <el-input v-model="filters.keyword" placeholder="订单号" maxlength="32" clearable />
        <el-button native-type="submit" :loading="loading">查询</el-button>
      </form>
      <div v-if="error" class="resource-stack">
        <el-alert :title="error" type="error" :closable="false" show-icon />
        <div><el-button @click="load">重试</el-button></div>
      </div>
      <el-table v-else v-loading="loading" :data="data?.items ?? []" row-key="id" empty-text="暂无订单">
        <el-table-column label="订单号" min-width="180">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">{{ row.order_no }}</el-button>
            <div class="resource-muted">{{ orderTime(row.created_at) }}</div>
          </template>
        </el-table-column>
        <el-table-column label="状态" min-width="140">
          <template #default="{ row }">
            {{ orderStatusLabels[row.status as OrderStatus] }}
            <el-tag v-if="row.review_overdue" type="danger" size="small" style="margin-left:6px">
              复核超时
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="资金" min-width="110">
          <template #default="{ row }">{{ fundStatusLabels[row.fund_status as FundStatus] }}</template>
        </el-table-column>
        <el-table-column label="金额" min-width="110">
          <template #default="{ row }">{{ formatFen(row.total_sale_fen) }}</template>
        </el-table-column>
        <el-table-column label="等待" width="100">
          <template #default="{ row }">{{ row.waiting_minutes }} 分钟</template>
        </el-table-column>
      </el-table>
      <div v-if="data && data.total > 20" class="resource-pagination">
        <el-pagination v-model:current-page="page" :page-size="20" :total="data.total"
          layout="total, prev, pager, next" @current-change="load" />
      </div>
    </div>

    <el-drawer :model-value="!!selected || detailLoading" title="订单详情" size="560px"
      @close="selected = undefined">
      <p v-if="detailLoading" role="status">正在加载…</p>
      <div v-else-if="selected" class="resource-stack">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="订单号">{{ selected.order_no }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ orderStatusLabels[selected.status] }}</el-descriptions-item>
          <el-descriptions-item label="资金">{{ fundStatusLabels[selected.fund_status as FundStatus] }}</el-descriptions-item>
          <el-descriptions-item label="售价 / 成本">
            {{ formatFen(selected.total_sale_fen) }} / {{ formatFen(selected.total_cost_fen) }}
          </el-descriptions-item>
          <el-descriptions-item label="联系人">
            {{ selected.contact_name }} · {{ selected.contact_phone }}
          </el-descriptions-item>
        </el-descriptions>

        <el-table :data="selected.items" size="small" row-key="id">
          <el-table-column v-if="selected.status === 'paid_pending_review'" label="缺货" width="73">
            <template #default="{ row }">
              <el-checkbox :model-value="stockouts.includes(row.id)" :aria-label="`${row.product_name} ${row.service_date} 缺货`"
                @change="(marked: unknown) => stockouts = marked ? [...stockouts, row.id] : stockouts.filter(id => id !== row.id)" />
            </template>
          </el-table-column>
          <el-table-column prop="product_name" label="商品" min-width="160" />
          <el-table-column prop="service_date" label="服务日" width="110" />
          <el-table-column prop="quantity" label="数量" width="70" />
          <el-table-column label="金额" width="100">
            <template #default="{ row }">{{ formatFen(row.subtotal_sale_fen) }}</template>
          </el-table-column>
        </el-table>

        <el-timeline>
          <el-timeline-item v-for="(event, index) in selected.events" :key="index"
            :timestamp="orderTime(event.created_at)">
            {{ event.kind }}<span v-if="event.actor_name"> · {{ event.actor_name }}</span>
            <span v-if="event.reason"> · {{ event.reason }}</span>
          </el-timeline-item>
        </el-timeline>

        <div class="resource-actions">
          <el-button v-if="selected.status === 'paid_pending_review'" type="primary"
            :loading="actionLoading" :disabled="stockouts.length > 0" @click="approve(selected)">通过复核</el-button>
          <el-button v-if="selected.status === 'paid_pending_review'" type="danger" plain
            :loading="actionLoading" @click="reject(selected)">拒绝（全额退款）</el-button>
        </div>
        <div v-if="selected.status === 'cancel_requested'" class="resource-stack">
          <el-select v-model="usage" aria-label="使用核实结果">
            <el-option value="unknown" label="使用情况待核实" />
            <el-option value="unused" label="已核实全部未使用" />
            <el-option value="used" label="至少一项已使用" />
          </el-select>
          <el-input v-model="supplierReply" type="textarea" maxlength="500" aria-label="实际供应商答复"
            placeholder="记录供应商实际答复或待核实的情况" />
          <div class="resource-actions">
            <el-button v-if="usage === 'unused'" type="primary" :disabled="!supplierReply.trim()" :loading="actionLoading"
              @click="resolveCancel(selected, true)">同意取消并退款</el-button>
            <el-button :disabled="!supplierReply.trim()" :loading="actionLoading" @click="resolveCancel(selected, false)">
              {{ usage === 'used' ? '转售后工单' : usage === 'unknown' ? '保存待核实记录' : '驳回申请' }}
            </el-button>
          </div>
        </div>
      </div>
    </el-drawer>
  </section>
</template>


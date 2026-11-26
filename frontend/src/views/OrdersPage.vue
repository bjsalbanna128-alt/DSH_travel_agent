<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminError } from '../api/adminResources'
import { ordersApi } from '../api/orders'
import { useAdminQuery } from '../composables/useAdminQuery'
import {
  formatFen, fundStatusLabels, orderStatusLabels, orderTime,
  type FundStatus, type OrderDetail, type OrderStatus, type OrderSummary,
} from '../types/orders'

const page = ref(1)
const status = ref<OrderStatus | ''>('')
const { data, loading, error, load } = useAdminQuery(signal =>
  ordersApi.mine({ status: status.value, page: page.value, page_size: 20 }, signal))

const selected = ref<OrderDetail>()
const detailLoading = ref(false)
const actionLoading = ref(false)

const pendingCount = computed(() =>
  (data.value?.items ?? []).filter(item => item.status === 'pending_payment').length)

async function openDetail(row: OrderSummary) {
  detailLoading.value = true
  selected.value = undefined
  try {
    selected.value = await ordersApi.detail(row.id, new AbortController().signal)
  } catch (failure) {
    ElMessage.error(adminError(failure))
  } finally {
    detailLoading.value = false
  }
}

async function pay(order: OrderDetail) {
  actionLoading.value = true
  try {
    selected.value = await ordersApi.pay(order.id, crypto.randomUUID())
    ElMessage.success('模拟支付成功，已付款等待平台确认')
    await load()
  } catch (failure) {
    ElMessage.error(adminError(failure))
  } finally {
    actionLoading.value = false
  }
}

async function cancel(order: OrderDetail) {
  const confirmed = await ElMessageBox.confirm(
    '取消后已付款将走全额模拟退款，确定取消？', '取消订单',
    { type: 'warning', confirmButtonText: '取消订单', cancelButtonText: '再想想' },
  ).then(() => true, () => false)
  if (!confirmed) return
  actionLoading.value = true
  try {
    selected.value = await ordersApi.cancel(order.id, '游客取消')
    ElMessage.success('订单已取消')
    await load()
  } catch (failure) {
    ElMessage.error(adminError(failure))
  } finally {
    actionLoading.value = false
  }
}

async function requestCancel(order: OrderDetail) {
  actionLoading.value = true
  try {
    selected.value = await ordersApi.requestCancel(order.id, '行程变化')
    ElMessage.success('已提交取消申请，等待平台与供应商核实')
    await load()
  } catch (failure) {
    ElMessage.error(adminError(failure))
  } finally {
    actionLoading.value = false
  }
}

function search() {
  page.value = 1
  void load()
}

onMounted(load)
</script>

<template>
  <section class="orders-page">
    <header class="orders-header">
      <h1>我的订单</h1>
      <div class="orders-filter">
        <el-select v-model="status" placeholder="全部状态" clearable aria-label="订单状态" @change="search">
          <el-option v-for="(label, value) in orderStatusLabels" :key="value" :label="label" :value="value" />
        </el-select>
        <el-button @click="load">刷新</el-button>
      </div>
    </header>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <p v-else-if="pendingCount" class="orders-hint" role="status">
      有 {{ pendingCount }} 笔订单待支付，15 分钟内未支付将自动关闭并释放库存。
    </p>

    <el-table v-loading="loading" :data="data?.items ?? []" row-key="id" empty-text="还没有订单">
      <el-table-column label="订单号" min-width="170">
        <template #default="{ row }">
          <el-button link type="primary" @click="openDetail(row)">{{ row.order_no }}</el-button>
          <div class="orders-muted">{{ orderTime(row.created_at) }}</div>
        </template>
      </el-table-column>
      <el-table-column label="状态" min-width="130">
        <template #default="{ row }">{{ orderStatusLabels[row.status as OrderStatus] }}</template>
      </el-table-column>
      <el-table-column label="资金" min-width="120">
        <template #default="{ row }">{{ fundStatusLabels[row.fund_status as FundStatus] }}</template>
      </el-table-column>
      <el-table-column label="金额" min-width="110">
        <template #default="{ row }">{{ formatFen(row.total_sale_fen) }}</template>
      </el-table-column>
      <el-table-column label="操作" min-width="150">
        <template #default="{ row }">
          <el-button v-if="row.status === 'pending_payment'" link type="primary" @click="openDetail(row)">
            去支付
          </el-button>
          <el-button v-else link @click="openDetail(row)">查看</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div v-if="data && data.total > 20" class="orders-pagination">
      <el-pagination v-model:current-page="page" :page-size="20" :total="data.total"
        layout="total, prev, pager, next" @current-change="load" />
    </div>

    <el-drawer :model-value="!!selected || detailLoading" title="订单详情" size="540px"
      @close="selected = undefined">
      <p v-if="detailLoading" role="status">正在加载…</p>
      <div v-else-if="selected" class="orders-detail">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="订单号">{{ selected.order_no }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ orderStatusLabels[selected.status] }}</el-descriptions-item>
          <el-descriptions-item label="资金">{{ fundStatusLabels[selected.fund_status as FundStatus] }}</el-descriptions-item>
          <el-descriptions-item label="金额">{{ formatFen(selected.total_sale_fen) }}</el-descriptions-item>
          <el-descriptions-item label="联系人">
            {{ selected.contact_name }} · {{ selected.contact_phone }}
          </el-descriptions-item>
          <el-descriptions-item v-if="selected.status === 'pending_payment'" label="支付截止">
            {{ orderTime(selected.expires_at) }}
          </el-descriptions-item>
          <el-descriptions-item v-if="selected.review_note" label="平台备注">
            {{ selected.review_note }}
          </el-descriptions-item>
        </el-descriptions>

        <h3>项目</h3>
        <el-table :data="selected.items" size="small" row-key="id">
          <el-table-column prop="product_name" label="商品" min-width="160" />
          <el-table-column prop="service_date" label="服务日" width="110" />
          <el-table-column prop="quantity" label="数量" width="70" />
          <el-table-column label="金额" width="100">
            <template #default="{ row }">{{ formatFen(row.subtotal_sale_fen) }}</template>
          </el-table-column>
        </el-table>

        <h3>出行人</h3>
        <el-table :data="selected.travelers" size="small">
          <el-table-column prop="name" label="姓名" min-width="100" />
          <el-table-column prop="document_mask" label="证件" min-width="130" />
          <el-table-column prop="phone_mask" label="电话" min-width="120" />
        </el-table>

        <h3>处理记录</h3>
        <el-timeline>
          <el-timeline-item v-for="(event, index) in selected.events" :key="index"
            :timestamp="orderTime(event.created_at)">
            {{ event.kind }}<span v-if="event.actor_name"> · {{ event.actor_name }}</span>
            <span v-if="event.reason"> · {{ event.reason }}</span>
          </el-timeline-item>
        </el-timeline>

        <div class="orders-actions">
          <el-button v-if="selected.status === 'pending_payment'" type="primary"
            :loading="actionLoading" @click="pay(selected)">
            模拟支付 {{ formatFen(selected.total_sale_fen) }}
          </el-button>
          <el-button v-if="['pending_payment', 'paid_pending_review'].includes(selected.status)"
            :loading="actionLoading" @click="cancel(selected)">取消订单</el-button>
          <el-button v-if="selected.status === 'confirmed'" :loading="actionLoading"
            @click="requestCancel(selected)">申请取消</el-button>
        </div>
        <p class="orders-note">模拟支付不会扣款，仅用于演示交易流程。</p>
      </div>
    </el-drawer>
  </section>
</template>

<style scoped>
.orders-page { max-width: 1000px; margin: 0 auto; padding: 20px 16px 40px; }
.orders-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.orders-header h1 { margin: 0; font-size: 22px; }
.orders-filter { display: flex; gap: 8px; align-items: center; }
.orders-hint { color: #b88230; font-size: 13px; margin: 0 0 12px; }
.orders-muted { color: #909399; font-size: 12px; }
.orders-pagination { margin-top: 12px; display: flex; justify-content: flex-end; }
.orders-detail h3 { margin: 16px 0 8px; font-size: 15px; }
.orders-actions { display: flex; gap: 8px; margin-top: 16px; }
.orders-note { color: #909399; font-size: 12px; margin-top: 8px; }
</style>


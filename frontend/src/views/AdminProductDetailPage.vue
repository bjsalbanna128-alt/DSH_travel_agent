<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { formatYuan } from '../adminPricing'
import { adminError, adminResources } from '../api/adminResources'
import ResourceOfferForm from '../components/ResourceOfferForm.vue'
import { useAdminQuery } from '../composables/useAdminQuery'
import { offerReasons, poiSourceLabels, productLabels, type OfferDay, type OfferStatus } from '../types/adminResources'
import { vehicleLabels } from '../types/checkout'

const route = useRoute()
const productId = computed(() => String(route.params.id))
const product = useAdminQuery(signal => adminResources.product(productId.value, signal))
const { data: record, loading: productLoading, error: productError } = product
const page = ref(1)
const queryMode = ref<'dates' | 'stay'>('dates')
const filters = reactive({ start: '', end: '', checkIn: '', checkOut: '', status: '' as OfferStatus | '' })
const active = ref<Record<string, string>>({})
const offers = useAdminQuery(signal => adminResources.offers(productId.value, {
  ...active.value, page: page.value, page_size: 20,
}, signal))
const { data: quotePage, loading: quotesLoading, error: quotesError } = offers
const editor = ref<{ mode: 'single' | 'batch'; day?: OfferDay }>()
const rowAction = ref('')

const attributes = computed(() => {
  const value = record.value?.attributes
  if (!value) return []
  if ('room_name' in value) {
    return [['房型名', value.room_name], ['可住人数', value.occupancy], ['早餐说明', value.breakfast]]
  }
  if ('ticket_name' in value) return [['票种名', value.ticket_name], ['适用人群', value.audience]]
  return [['车型名', value.vehicle_name], ['可乘客数', value.passenger_capacity],
    ['车型编码', value.model_code ?? '待补齐'], ['用途', value.purpose ? vehicleLabels[value.purpose] : '待补齐'],
    ['行李容量', value.luggage_capacity ?? '待补齐']]
})

function search() {
  if (queryMode.value === 'stay' && (!filters.checkIn || !filters.checkOut)) {
    ElMessage.warning('请填写入住日和退房日。')
    return
  }
  page.value = 1
  active.value = queryMode.value === 'stay'
    ? { check_in: filters.checkIn, check_out: filters.checkOut, status: filters.status }
    : { start_date: filters.start, end_date: filters.end, status: filters.status }
  void offers.load()
}

function today() {
  const local = new Date()
  const date = [local.getFullYear(), local.getMonth() + 1, local.getDate()]
    .map(part => String(part).padStart(2, '0')).join('-')
  queryMode.value = 'dates'
  filters.start = date
  filters.end = date
  filters.status = ''
  search()
}

function resetQuery() {
  Object.assign(filters, { start: '', end: '', checkIn: '', checkOut: '', status: '' })
  queryMode.value = 'dates'
  active.value = {}
  page.value = 1
}

watch(productId, () => {
  editor.value = undefined
  resetQuery()
  product.clear()
  offers.clear()
  void product.load()
  void offers.load()
}, { immediate: true })

function clearFilters() {
  resetQuery()
  void offers.load()
}

async function refreshQuotes() {
  editor.value = undefined
  await Promise.all([product.load(), offers.load()])
  if (page.value > 1 && quotePage.value && !quotePage.value.items.length) {
    page.value = Math.max(1, Math.ceil(quotePage.value.total / 20))
    await offers.load()
  }
}

async function changeOfferStatus(day: OfferDay) {
  if (!day.quote || rowAction.value) return
  const stopping = day.quote.status === 'available'
  rowAction.value = day.service_date
  try {
    await adminResources.updateOffer(productId.value, day.service_date, { status: stopping ? 'stopped' : 'available' })
    ElMessage.success(stopping ? '当日报价已停售' : '当日报价已恢复')
    await refreshQuotes()
  } catch (failure) {
    ElMessage.error(adminError(failure))
  } finally {
    rowAction.value = ''
  }
}

async function removeOffer(day: OfferDay) {
  const confirmed = await ElMessageBox.confirm(
    `删除 ${day.service_date} 的报价后，当天会恢复为未报价。`, '删除报价',
    { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
  ).then(() => true, () => false)
  if (!confirmed) return
  rowAction.value = day.service_date
  try {
    await adminResources.deleteOffer(productId.value, day.service_date)
    ElMessage.success('报价已删除')
    await refreshQuotes()
  } catch (failure) {
    ElMessage.error(adminError(failure))
  } finally {
    rowAction.value = ''
  }
}
</script>

<template>
  <section class="resource-page">
    <header class="resource-titlebar">
      <div>
        <router-link class="resource-link" :to="{ name: 'admin-products' }">返回商品列表</router-link>
        <h1>{{ record?.name ?? '商品详情' }}</h1>
      </div>
    </header>

    <div v-if="productError" class="resource-panel resource-stack">
      <el-alert :title="productError" type="error" show-icon :closable="false" />
      <div><el-button @click="product.load">重试</el-button></div>
    </div>
    <p v-else-if="!record && productLoading" role="status">正在加载商品…</p>
    <template v-else-if="record">
      <div class="resource-panel">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="供应商">
            {{ record.supplier_name }}
            <el-tag v-if="record.supplier_status === 'inactive'" type="info" size="small">停用</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="上架状态">
            <el-tag :type="record.status === 'on_shelf' ? 'success' : 'info'">{{ record.status === 'on_shelf' ? '上架' : '下架' }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="商品类型">{{ productLabels[record.type] }}</el-descriptions-item>
          <el-descriptions-item label="城市">{{ record.city }}</el-descriptions-item>
          <el-descriptions-item label="POI">
            {{ record.poi ? `${record.poi.name} · ${poiSourceLabels[record.poi.source]}` : '未绑定' }}
          </el-descriptions-item>
          <el-descriptions-item label="计价单位">人民币元 / {{ record.price_unit }}</el-descriptions-item>
          <el-descriptions-item v-for="[label, value] in attributes" :key="label" :label="String(label)">{{ value }}</el-descriptions-item>
        </el-descriptions>
      </div>

      <div class="resource-panel">
        <header class="resource-titlebar">
          <h2>每日报价 <span class="resource-muted">{{ record.offer_count }} 条</span></h2>
          <div class="resource-actions">
            <el-button @click="editor = { mode: 'batch' }">批量填价</el-button>
            <el-button type="primary" @click="editor = { mode: 'single' }">新增单日报价</el-button>
          </div>
        </header>
        <el-radio-group v-if="record.type === 'hotel_room'" v-model="queryMode" class="quote-query-mode" aria-label="报价查询方式">
          <el-radio-button value="dates">服务日期</el-radio-button>
          <el-radio-button value="stay">酒店跨夜核对</el-radio-button>
        </el-radio-group>
        <form class="resource-toolbar" @submit.prevent="search">
          <template v-if="queryMode === 'stay'">
            <span>入住日</span><el-input v-model="filters.checkIn" type="date" aria-label="入住日" class="resource-date" />
            <span>退房日</span><el-input v-model="filters.checkOut" type="date" aria-label="退房日" class="resource-date" />
          </template>
          <template v-else>
            <span>开始日期</span><el-input v-model="filters.start" type="date" aria-label="报价查询开始日期" class="resource-date" />
            <span>结束日期</span><el-input v-model="filters.end" type="date" aria-label="报价查询结束日期" class="resource-date" />
          </template>
          <el-select v-model="filters.status" aria-label="按报价状态筛选" placeholder="全部报价状态" clearable value-on-clear="">
            <el-option label="可售" value="available" /><el-option label="停售" value="stopped" />
          </el-select>
          <el-button native-type="submit" :loading="quotesLoading">查询</el-button>
          <el-button @click="today">查今天</el-button>
          <el-button @click="clearFilters">清除筛选</el-button>
        </form>

        <div v-if="quotesError" class="resource-stack">
          <el-alert :title="quotesError" type="error" show-icon :closable="false" />
          <div><el-button @click="offers.load">重试</el-button></div>
        </div>
        <template v-else>
          <section v-if="quotePage?.stay" class="stay-summary" aria-label="跨夜核对结果">
            <div class="resource-actions">
              <strong>{{ quotePage.stay.check_in }} 至 {{ quotePage.stay.check_out }}，{{ quotePage.stay.nights }} 晚</strong>
              <el-tag :type="quotePage.stay.can_sell ? 'success' : 'warning'">{{ quotePage.stay.can_sell ? '整段可售' : '整段不可售' }}</el-tag>
              <span>成本合计 {{ formatYuan(quotePage.stay.cost_fen) }}</span>
              <span>售价合计 {{ formatYuan(quotePage.stay.sale_fen) }}</span>
            </div>
            <ul v-if="quotePage.stay.unavailable.length" class="stay-unavailable">
              <li v-for="day in quotePage.stay.unavailable" :key="day.service_date">
                {{ day.service_date }} {{ day.reasons.map(reason => offerReasons[reason]).join('、') }}
              </li>
            </ul>
          </section>
          <el-table v-loading="quotesLoading" class="resource-table" :data="quotePage?.items ?? []"
            row-key="service_date" empty-text="暂无匹配的报价">
            <el-table-column label="服务日期" prop="service_date" width="124" />
            <el-table-column label="成本" min-width="110">
              <template #default="{ row }">{{ formatYuan(row.quote?.cost_fen) }}</template>
            </el-table-column>
            <el-table-column label="对客售价" min-width="125">
              <template #default="{ row }">
                {{ formatYuan(row.quote?.sale_fen) }}
                <el-tag v-if="row.quote?.below_cost" type="warning" size="small">低于成本</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="报价状态" width="100">
              <template #default="{ row }">{{ row.quote ? (row.quote.status === 'available' ? '可售' : '停售') : '未报价' }}</template>
            </el-table-column>
            <el-table-column label="投放 / 剩余" min-width="130">
              <template #default="{ row }">
                <template v-if="row.quote">
                  <span v-if="row.quote.total_quantity !== null">
                    {{ row.quote.total_quantity }} / <strong>{{ row.quote.remaining }}</strong>
                  </span>
                  <span v-else class="unavailable-reason">未核定</span>
                </template>
                <span v-else class="resource-muted">—</span>
              </template>
            </el-table-column>
            <el-table-column label="预占 / 确认" min-width="120">
              <template #default="{ row }">
                <span v-if="row.quote">{{ row.quote.reserved_quantity }} / {{ row.quote.confirmed_quantity }}</span>
                <span v-else class="resource-muted">—</span>
              </template>
            </el-table-column>
            <el-table-column label="实际可售" min-width="150">
              <template #default="{ row }">
                <el-tag v-if="row.can_sell" type="success">可售</el-tag>
                <span v-else class="unavailable-reason">{{ (row as OfferDay).reasons.map(reason => offerReasons[reason]).join('、') }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" min-width="170">
              <template #default="{ row }">
                <div class="resource-actions">
                  <el-button link type="primary" @click="editor = { mode: 'single', day: row }">{{ row.quote ? '改价' : '新增' }}</el-button>
                  <template v-if="row.quote">
                    <el-button link :disabled="!!rowAction" @click="changeOfferStatus(row)">{{ row.quote.status === 'available' ? '停售' : '恢复' }}</el-button>
                    <el-button link type="danger" :disabled="!!rowAction" @click="removeOffer(row)">删除</el-button>
                  </template>
                </div>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="quotePage" class="resource-pagination">
            <el-pagination v-model:current-page="page" :page-size="20" :total="quotePage.total"
              layout="total, prev, pager, next" @current-change="offers.load" />
          </div>
        </template>
      </div>

      <ResourceOfferForm v-if="editor" :product-id="record.id" :price-unit="record.price_unit"
        :mode="editor.mode" :day="editor.day" @close="editor = undefined" @saved="refreshQuotes" />
    </template>
  </section>
</template>

<style scoped>
.resource-titlebar h1 { margin-top: 8px; }
.quote-query-mode { margin-bottom: 12px; }
.stay-summary { display: grid; gap: 8px; padding: 12px 14px; margin-bottom: 16px; border-radius: 6px; background: #edf3ff; }
.stay-unavailable { list-style: none; max-height: 120px; overflow: auto; }
.stay-unavailable li + li { margin-top: 4px; }
.unavailable-reason { color: #805113; }
</style>

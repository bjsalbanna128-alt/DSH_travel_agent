<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminError } from '../api/adminResources'
import {
  fulfillmentApi, formatTime, taskStatusLabels, taskTypeLabels,
  type ResourceOption, type TaskDetail, type TaskStatus, type TaskType,
} from '../api/fulfillment'
import { useAdminQuery } from '../composables/useAdminQuery'

const tab = ref<'tasks' | 'board'>('tasks')
const page = ref(1)
const filters = reactive({ status: '' as TaskStatus | '', task_type: '' as TaskType | '', service_date: '' })
const tasks = useAdminQuery(signal => fulfillmentApi.tasks(
  { ...filters, page: page.value, page_size: 20 }, signal))
const board = useAdminQuery(signal => fulfillmentApi.board(7, signal))

const detail = ref<TaskDetail>()
const busy = ref(false)
const credential = reactive({ voucher_no: '', confirmation_no: '' })
const dispatcher = ref(false)
const candidates = ref<{ vehicles: ResourceOption[]; drivers: ResourceOption[] }>()
const chosen = reactive({ vehicle: '', driver: '' })

function openDetail(row: { id: string }) {
  void loadDetail(row.id)
}

async function loadDetail(id: string) {
  detail.value = undefined
  try {
    const payload = await fulfillmentApi.task(id)
    detail.value = payload
    credential.voucher_no = payload.voucher_no
    credential.confirmation_no = payload.confirmation_no
  } catch (failure) {
    ElMessage.error(adminError(failure))
  }
}

async function act(run: () => Promise<TaskDetail>) {
  if (!detail.value) return
  busy.value = true
  try {
    detail.value = await run()
    ElMessage.success('操作成功')
    await tasks.load()
    await board.load()
  } catch (failure) {
    ElMessage.error(adminError(failure))
  } finally {
    busy.value = false
  }
}

function confirmCredentials() {
  if (!detail.value) return
  void act(() => fulfillmentApi.confirm(detail.value!.id, { ...credential, expected_version: detail.value!.version }))
}

function markException() {
  void ElMessageBox.prompt('请填写异常原因（运营可见）', '登记异常', {
    inputPattern: /\S+/, inputErrorMessage: '原因不能为空',
  }).then(result => act(() => fulfillmentApi.exception(detail.value!.id, result.value, detail.value!.version)),
    () => undefined)
}

function cancelTask() {
  void ElMessageBox.prompt('请填写作废原因', '作废任务', {
    inputPattern: /\S+/, inputErrorMessage: '原因不能为空',
  }).then(result => act(() => fulfillmentApi.cancel(detail.value!.id, result.value, detail.value!.version)),
    () => undefined)
}

async function openDispatcher() {
  if (!detail.value) return
  dispatcher.value = true
  candidates.value = undefined
  chosen.vehicle = ''
  chosen.driver = ''
  try {
    candidates.value = await fulfillmentApi.candidates(detail.value.id)
  } catch (failure) {
    ElMessage.error(adminError(failure))
  }
}

async function assign() {
  if (!detail.value || !chosen.vehicle || !chosen.driver) {
    ElMessage.warning('请选择车辆与司机。')
    return
  }
  dispatcher.value = false
  await act(() => fulfillmentApi.assign(detail.value!.id, chosen.vehicle, chosen.driver,
    detail.value!.version))
}

function search() {
  page.value = 1
  void tasks.load()
}

function switchTab(next: 'tasks' | 'board') {
  tab.value = next
  if (next === 'board') void board.load()
}

onMounted(() => {
  void tasks.load()
  void board.load()
})
</script>

<template>
  <section class="resource-page">
    <header class="resource-titlebar">
      <h1>履约任务</h1>
      <div class="resource-actions">
        <el-radio-group :model-value="tab" @update:model-value="(value: string | number | boolean | undefined) => switchTab(value === 'board' ? 'board' : 'tasks')">
          <el-radio-button value="tasks">任务</el-radio-button>
          <el-radio-button value="board">看板</el-radio-button>
        </el-radio-group>
      </div>
    </header>

    <div v-if="tab === 'tasks'" class="resource-panel">
      <form class="resource-toolbar" @submit.prevent="search">
        <el-select v-model="filters.status" placeholder="全部状态" clearable aria-label="状态筛选">
          <el-option v-for="(label, value) in taskStatusLabels" :key="value" :label="label" :value="value" />
        </el-select>
        <el-select v-model="filters.task_type" placeholder="全部类型" clearable aria-label="类型筛选">
          <el-option v-for="(label, value) in taskTypeLabels" :key="value" :label="label" :value="value" />
        </el-select>
        <el-input v-model="filters.service_date" type="date" aria-label="服务日期" />
        <el-button native-type="submit" :loading="tasks.loading.value">查询</el-button>
      </form>
      <div v-if="tasks.error.value" class="resource-stack">
        <el-alert :title="tasks.error.value" type="error" :closable="false" show-icon />
        <div><el-button @click="tasks.load()">重试</el-button></div>
      </div>
      <el-table v-else v-loading="tasks.loading.value" :data="tasks.data.value?.items ?? []" row-key="id"
        empty-text="暂无任务">
        <el-table-column label="任务" min-width="180">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">{{ row.product_name || taskTypeLabels[row.task_type as TaskType] }}</el-button>
            <div class="resource-muted">{{ taskTypeLabels[row.task_type as TaskType] }} · {{ row.quantity }} 份</div>
          </template>
        </el-table-column>
        <el-table-column label="服务日" width="120">
          <template #default="{ row }">{{ row.service_date }}<span v-if="row.start_time"> {{ row.start_time }}</span></template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'exception' ? 'danger' : row.status === 'completed' ? 'success' : 'info'">
              {{ taskStatusLabels[row.status as TaskStatus] }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="supplier_name" label="供应商" min-width="120" />
        <el-table-column label="订单" min-width="120">
          <template #default="{ row }"><span class="resource-muted">{{ row.order_id }}</span></template>
        </el-table-column>
      </el-table>
      <div v-if="tasks.data.value && tasks.data.value.total > 20" class="resource-pagination">
        <el-pagination v-model:current-page="page" :page-size="20" :total="tasks.data.value.total"
          layout="total, prev, pager, next" @current-change="tasks.load()" />
      </div>
    </div>

    <div v-else class="resource-panel">
      <p class="resource-muted">今日 {{ board.data.value?.today }}，未来 7 天共 {{ board.data.value?.total ?? 0 }} 个任务。</p>
      <el-alert type="info" :closable="false" show-icon
        title="「销售已承诺」是总口径；「已指派」「待派」是其中的子集，不要相加。" />
      <el-table :data="board.data.value?.per_day ?? []" row-key="date" size="small">
        <el-table-column prop="date" label="日期" width="120" />
        <el-table-column prop="committed" label="销售已承诺" width="110" />
        <el-table-column prop="assigned" label="已指派" width="90" />
        <el-table-column prop="unassigned" label="待派" width="90" />
        <el-table-column prop="pending" label="待处理" width="90" />
        <el-table-column prop="ready" label="已就绪" width="90" />
        <el-table-column prop="in_progress" label="进行中" width="90" />
      </el-table>
      <h3>异常 {{ board.data.value?.exceptions.length ?? 0 }} 项</h3>
      <el-table :data="board.data.value?.exceptions ?? []" row-key="id" size="small" empty-text="没有异常">
        <el-table-column label="任务" min-width="140">
          <template #default="{ row }">{{ taskTypeLabels[row.task_type as TaskType] }}</template>
        </el-table-column>
        <el-table-column prop="service_date" label="服务日" width="120" />
        <el-table-column prop="reason" label="原因" min-width="200" />
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-drawer :model-value="!!detail" title="任务详情" size="560px" @close="detail = undefined">
      <div v-if="detail" class="resource-stack">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="类型">{{ taskTypeLabels[detail.task_type] }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ taskStatusLabels[detail.status] }}</el-descriptions-item>
          <el-descriptions-item label="服务日">{{ detail.service_date }} {{ detail.start_time ?? '' }}</el-descriptions-item>
          <el-descriptions-item label="商品">{{ detail.product_name }} × {{ detail.quantity }}</el-descriptions-item>
          <el-descriptions-item label="票号 / 确认号">
            {{ detail.voucher_no || '—' }} / {{ detail.confirmation_no || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="当前指派">
            <template v-if="detail.assignment">
              车辆 {{ detail.assignment.vehicle_id }} · 司机 {{ detail.assignment.driver_id }}
            </template>
            <template v-else>未指派</template>
          </el-descriptions-item>
          <el-descriptions-item v-if="detail.exception_reason" label="异常原因">
            {{ detail.exception_reason }}
          </el-descriptions-item>
        </el-descriptions>

        <div v-if="detail.status === 'pending'" class="resource-actions">
          <el-input v-model="credential.voucher_no" placeholder="票号" maxlength="64" />
          <el-input v-model="credential.confirmation_no" placeholder="供应商确认号" maxlength="64" />
          <el-button type="primary" :loading="busy" @click="confirmCredentials">登记凭证</el-button>
        </div>

        <div class="resource-actions">
          <el-button v-if="detail.status === 'ready'" type="primary" :loading="busy"
            @click="act(() => fulfillmentApi.start(detail!.id, detail!.version))">开始</el-button>
          <el-button v-if="detail.status === 'in_progress'" type="primary" :loading="busy"
            @click="act(() => fulfillmentApi.complete(detail!.id, detail!.version))">完成</el-button>
          <el-button v-if="detail.task_type === 'vehicle_pickup' || detail.task_type === 'vehicle_charter'"
            :loading="busy" @click="openDispatcher">派车</el-button>
          <el-button v-if="detail.assignment" :loading="busy"
            @click="act(() => fulfillmentApi.release(detail!.id, detail!.version))">撤派</el-button>
          <el-button v-if="detail.status === 'exception'" :loading="busy"
            @click="act(() => fulfillmentApi.recover(detail!.id, detail!.version))">恢复</el-button>
          <el-button v-if="detail.status !== 'exception' && detail.status !== 'cancelled' && detail.status !== 'completed'"
            :loading="busy" @click="markException">登记异常</el-button>
          <el-button v-if="detail.status !== 'cancelled' && detail.status !== 'completed'"
            type="danger" plain :loading="busy" @click="cancelTask">作废</el-button>
        </div>

        <h3>处理记录</h3>
        <el-timeline>
          <el-timeline-item v-for="(event, index) in detail.events" :key="index"
            :timestamp="formatTime(event.created_at)">
            {{ event.kind }}：{{ event.from_status ?? '—' }} → {{ event.to_status ?? '—' }}
            <span v-if="event.actor_name"> · {{ event.actor_name }}</span>
            <span v-if="event.reason"> · {{ event.reason }}</span>
          </el-timeline-item>
        </el-timeline>
      </div>
    </el-drawer>

    <el-dialog v-model="dispatcher" title="指派车辆与司机" width="520px">
      <p class="resource-muted">只列出该车队在该时段空闲的资源。</p>
      <el-select v-model="chosen.vehicle" placeholder="选择车辆" class="picker">
        <el-option v-for="vehicle in candidates?.vehicles ?? []" :key="vehicle.id"
          :label="`${vehicle.plate_no} · ${vehicle.model_name}（${vehicle.seats} 座）`" :value="vehicle.id" />
      </el-select>
      <el-select v-model="chosen.driver" placeholder="选择司机" class="picker">
        <el-option v-for="driver in candidates?.drivers ?? []" :key="driver.id"
          :label="`${driver.name} · ${driver.license_type}`" :value="driver.id" />
      </el-select>
      <template #footer>
        <el-button @click="dispatcher = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="assign">确认指派</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.picker { width: 100%; margin-bottom: 10px; }
</style>



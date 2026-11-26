<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminError, adminQueryString, adminRequest, adminResources } from '../api/adminResources'
import { useAdminQuery } from '../composables/useAdminQuery'
import type { PageResult, SupplierStatus } from '../types/adminResources'

interface Model { code: string; name: string }
interface RosterRecord { id: string; supplier_id: string; status: SupplierStatus; notes: string }
interface Vehicle extends RosterRecord {
  plate_no: string; model_code: string | null; model_name: string; seats: number; luggage: number
}
interface Driver extends RosterRecord {
  name: string; phone: string; license_type: string; service_cities: string[]; model_codes: string[] | null
}
interface Capacity {
  available: number
  service_date: string
  daily: { product_id: string; name: string; total_quantity: number | null;
    reserved_quantity: number; confirmed_quantity: number; remaining_quantity: number | null }[]
}

const supplier = ref('')
const supplierName = ref('')
const tab = ref<'vehicles' | 'drivers'>('vehicles')
const page = ref(1)
const roster = useAdminQuery(signal => adminRequest<PageResult<Vehicle | Driver>>(
  '/fleet/' + tab.value + adminQueryString({ supplier_id: supplier.value, page: page.value }), { signal }))
const models = useAdminQuery(signal => adminRequest<Model[]>(
  '/fleet/models' + adminQueryString({ supplier_id: supplier.value }), { signal }))
const suppliers = useAdminQuery(signal => adminResources.suppliers(
  { kind: 'vehicle_fleet', name: supplierName.value, page_size: 100 }, signal))
const eligibleFleets = computed(() => suppliers.data.value?.items.filter(row => ['北京', '北京市'].includes(row.fleet_city ?? '')) ?? [])
const availability = reactive({ model_code: '', start: '', end: '', passengers: 1, luggage: 0 })
const capacity = useAdminQuery(signal => adminRequest<Capacity>('/fleet/capacity' + adminQueryString({
  supplier_id: supplier.value, model_code: availability.model_code,
  starts_at: availability.start + ':00+08:00', ends_at: availability.end + ':00+08:00',
  passengers: availability.passengers, luggage: availability.luggage,
}), { signal }))

const editor = ref<'vehicles' | 'drivers' | 'models'>()
const editing = ref('')
const saving = ref(false)
const actionError = ref('')
const form = reactive({ status: 'active' as SupplierStatus, notes: '', code: '', name: '', plate_no: '',
  model_code: '', seats: 4, luggage: 0, phone: '', license_type: '', cities: '北京', model_codes: [] as string[] })
const selectedModel = (code: string) => models.data.value?.find(model => model.code === code)?.name ?? code

async function searchFleets(name = '') {
  supplierName.value = name
  await suppliers.load()
  if (!supplier.value) supplier.value = eligibleFleets.value[0]?.id ?? ''
}
onMounted(() => searchFleets())
watch(supplier, () => {
  models.clear()
  availability.model_code = ''
  actionError.value = ''
  if (supplier.value) void models.load()
})
watch([supplier, tab], () => {
  roster.clear()
  page.value = 1
  if (supplier.value) void roster.load()
})
watch(() => ({ ...availability }), capacity.clear)

function open(kind: 'vehicles' | 'drivers' | 'models', row?: Vehicle | Driver | Model) {
  actionError.value = ''
  editing.value = row ? ('id' in row ? row.id : row.code) : ''
  Object.assign(form, { status: row && 'status' in row ? row.status : 'active',
    notes: row && 'notes' in row ? row.notes : '', code: row && 'code' in row ? row.code : '',
    name: row && 'name' in row ? row.name : '', plate_no: row && 'plate_no' in row ? row.plate_no : '',
    model_code: row && 'model_code' in row ? row.model_code || '' : '', seats: row && 'seats' in row ? row.seats : 4,
    luggage: row && 'luggage' in row ? row.luggage : 0, phone: row && 'phone' in row ? row.phone : '',
    license_type: row && 'license_type' in row ? row.license_type : '',
    cities: row && 'service_cities' in row ? row.service_cities.join('、') : '北京',
    model_codes: row && 'model_codes' in row ? [...(row.model_codes ?? [])] : [],
  })
  editor.value = kind
}

function path(kind: string, key = '', suffix = '') {
  return '/fleet/' + kind + (key ? '/' + encodeURIComponent(key) + suffix : '')
    + (kind === 'models' ? adminQueryString({ supplier_id: supplier.value }) : '')
}

async function refresh(kind: string) {
  capacity.clear()
  if (kind === 'models') await models.load()
  else await roster.load()
}

async function save() {
  const kind = editor.value
  if (!kind || saving.value) return
  saving.value = true
  actionError.value = ''
  const rosterFields = { supplier_id: supplier.value, status: form.status, notes: form.notes }
  const body = kind === 'models' ? (editing.value ? { name: form.name } : { code: form.code, name: form.name })
    : kind === 'vehicles' ? { ...rosterFields, plate_no: form.plate_no, model_code: form.model_code,
      seats: form.seats, luggage: form.luggage }
    : { ...rosterFields, name: form.name, phone: form.phone, license_type: form.license_type,
      service_cities: form.cities.split(/[、,，]/).map(city => city.trim()).filter(Boolean), model_codes: form.model_codes }
  try {
    await adminRequest(path(kind, editing.value), { method: editing.value ? 'PATCH' : 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    editor.value = undefined
    ElMessage.success('已保存')
    await refresh(kind)
  } catch (failure) {
    actionError.value = adminError(failure)
  } finally {
    saving.value = false
  }
}

async function changeStatus(kind: string, key: string, remove = false) {
  if (saving.value) return
  try {
    await ElMessageBox.confirm(remove ? '确认删除这条车队台账记录？' : '确认停用这条车队台账记录？', '车队台账',
      { confirmButtonText: '确认', cancelButtonText: '取消' })
  } catch { return }
  saving.value = true
  actionError.value = ''
  try {
    await adminRequest(path(kind, key, remove ? '' : '/disable'), { method: remove ? 'DELETE' : 'POST' })
    await refresh(kind)
  } catch (failure) {
    actionError.value = adminError(failure)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="resource-stack fleet-page">
    <h1>车队台账</h1>
    <div class="resource-actions">
      <label for="fleet-supplier">北京车队</label>
      <el-select id="fleet-supplier" v-model="supplier" filterable remote :remote-method="searchFleets" aria-label="北京车队"
        placeholder="选择或搜索北京车队" :loading="suppliers.loading.value" style="width: 280px">
        <el-option v-for="row in eligibleFleets" :key="row.id" :value="row.id"
          :label="row.name + (row.status === 'inactive' ? '（已停用）' : '')" />
      </el-select>
      <router-link to="/admin/suppliers">管理供应商</router-link>
    </div>
    <el-alert v-if="suppliers.error.value || (!editor && actionError)" :title="suppliers.error.value || actionError" type="error" :closable="false" />
    <el-empty v-if="!supplier && !suppliers.loading.value && !suppliers.error.value" description="请先在供应商管理中登记服务城市为北京的车队。" />
    <template v-if="supplier">
      <el-alert v-if="models.error.value || roster.error.value" :title="models.error.value || roster.error.value" type="error" :closable="false" />
      <el-tabs v-model="tab">
        <el-tab-pane label="车辆" name="vehicles" />
        <el-tab-pane label="司机" name="drivers" />
      </el-tabs>
      <template v-if="tab === 'vehicles'">
        <div class="resource-actions">
          <h2>车型</h2>
          <el-button @click="open('models')">新增车型</el-button>
        </div>
        <el-table v-loading="models.loading.value" :data="models.data.value ?? []">
          <el-table-column label="车型编码" prop="code" />
          <el-table-column label="车型名称" prop="name" />
          <el-table-column label="操作" width="160">
            <template #default="{ row }">
              <el-button link @click="open('models', row)">改名</el-button>
              <el-button link type="danger" :disabled="saving" @click="changeStatus('models', row.code, true)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </template>

      <div class="resource-actions">
        <h2>{{ tab === 'vehicles' ? '车辆记录' : '司机记录' }}</h2>
        <el-button type="primary" @click="open(tab)">{{ tab === 'vehicles' ? '新增车辆' : '新增司机' }}</el-button>
      </div>
      <el-table :key="tab" v-loading="roster.loading.value" :data="roster.data.value?.items ?? []">
        <template v-if="tab === 'vehicles'">
          <el-table-column label="车牌" prop="plate_no" />
          <el-table-column label="车型">
            <template #default="{ row }">{{ row.model_code ? selectedModel(row.model_code) : row.model_name || '待登记' }}</template>
          </el-table-column>
          <el-table-column label="可乘人数" prop="seats" />
          <el-table-column label="行李容量" prop="luggage" />
        </template>
        <template v-else>
          <el-table-column label="司机姓名" prop="name" />
          <el-table-column label="运营联系电话" prop="phone" min-width="145" />
          <el-table-column label="驾驶资格" prop="license_type" />
          <el-table-column label="服务城市">
            <template #default="{ row }">{{ row.service_cities.join('、') }}</template>
          </el-table-column>
          <el-table-column label="可服务车型">
            <template #default="{ row }">{{ row.model_codes?.map(selectedModel).join('、') || '待登记' }}</template>
          </el-table-column>
        </template>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">{{ row.status === 'active' ? '启用' : '停用' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button link @click="open(tab, row)">编辑</el-button>
            <el-button v-if="row.status === 'active'" link :disabled="saving" @click="changeStatus(tab, row.id)">停用</el-button>
            <el-button link type="danger" :disabled="saving" @click="changeStatus(tab, row.id, true)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination v-model:current-page="page" :page-size="20" :total="roster.data.value?.total ?? 0"
        layout="total, prev, pager, next" @current-change="roster.load" />

      <h2>时段运力</h2>
      <form class="fleet-fields" @submit.prevent="capacity.load">
        <label>车型
          <select v-model="availability.model_code" required>
            <option value="" disabled>选择车型</option>
            <option v-for="model in models.data.value" :key="model.code" :value="model.code">{{ model.name }}</option>
          </select>
        </label>
        <label>开始（北京时间）<input v-model="availability.start" type="datetime-local" required /></label>
        <label>结束（北京时间）<input v-model="availability.end" type="datetime-local" required /></label>
        <label>乘客数<input v-model.number="availability.passengers" type="number" min="1" max="100" required /></label>
        <label>行李件数<input v-model.number="availability.luggage" type="number" min="0" max="100" required /></label>
        <el-button native-type="submit" :loading="capacity.loading.value">查询运力</el-button>
      </form>
      <el-alert v-if="capacity.error.value" :title="capacity.error.value" type="error" :closable="false" />
      <template v-if="capacity.data.value">
        <p>指定时段剩余 <strong>{{ capacity.data.value.available }}</strong> 趟</p>
        <p>按开始日 {{ capacity.data.value.service_date }} 核对日投放。</p>
        <el-table :data="capacity.data.value.daily">
          <el-table-column label="商品" prop="name" min-width="180" />
          <el-table-column label="日投放">
            <template #default="{ row }">{{ row.total_quantity ?? '待核定' }}</template>
          </el-table-column>
          <el-table-column label="预占" prop="reserved_quantity" />
          <el-table-column label="已确认" prop="confirmed_quantity" />
          <el-table-column label="日余量">
            <template #default="{ row }">{{ row.remaining_quantity ?? '待核定' }}</template>
          </el-table-column>
        </el-table>
      </template>
    </template>

    <el-dialog v-if="editor" :model-value="true" :title="(editing ? '编辑' : '新增') + ({ vehicles: '车辆', drivers: '司机', models: '车型' })[editor]"
      width="540px" :close-on-click-modal="!saving" @update:model-value="(open: boolean) => { if (!open && !saving) editor = undefined }">
      <el-alert v-if="actionError" :title="actionError" type="error" :closable="false" />
      <el-form label-position="top" :disabled="saving" @submit.prevent="save">
        <template v-if="editor === 'models'">
          <el-form-item label="车型编码"><el-input v-model.trim="form.code" maxlength="40" :disabled="!!editing" /></el-form-item>
          <el-form-item label="车型名称"><el-input v-model.trim="form.name" maxlength="80" /></el-form-item>
        </template>
        <template v-else>
          <template v-if="editor === 'vehicles'">
            <el-form-item label="车牌"><el-input v-model.trim="form.plate_no" maxlength="16" /></el-form-item>
            <el-form-item label="车型">
              <el-select v-model="form.model_code" aria-label="车辆车型">
                <el-option v-for="model in models.data.value" :key="model.code" :value="model.code" :label="model.name" />
              </el-select>
            </el-form-item>
            <el-form-item label="可乘人数（不含司机）"><el-input-number v-model="form.seats" :min="1" :max="100" :precision="0" /></el-form-item>
            <el-form-item label="行李容量"><el-input-number v-model="form.luggage" :min="0" :max="100" :precision="0" /></el-form-item>
          </template>
          <template v-else>
            <el-form-item label="司机姓名"><el-input v-model.trim="form.name" maxlength="50" /></el-form-item>
            <el-form-item label="运营联系电话"><el-input v-model.trim="form.phone" maxlength="32" /></el-form-item>
            <el-form-item label="驾驶资格"><el-input v-model.trim="form.license_type" maxlength="16" /></el-form-item>
            <el-form-item label="服务城市"><el-input v-model.trim="form.cities" placeholder="多个城市用顿号分隔" /></el-form-item>
            <el-form-item label="可服务车型">
              <el-select v-model="form.model_codes" multiple aria-label="司机可服务车型">
                <el-option v-for="model in models.data.value" :key="model.code" :value="model.code" :label="model.name" />
              </el-select>
            </el-form-item>
          </template>
          <el-form-item label="状态">
            <el-select v-model="form.status" aria-label="台账状态">
              <el-option label="启用" value="active" /><el-option label="停用" value="inactive" />
            </el-select>
          </el-form-item>
          <el-form-item label="备注"><el-input v-model="form.notes" type="textarea" maxlength="1000" /></el-form-item>
        </template>
        <el-button native-type="submit" type="primary" :loading="saving">保存</el-button>
      </el-form>
    </el-dialog>
  </section>
</template>

<style scoped>
.fleet-page h2 { font-size: 17px; margin: 8px 0; }
.fleet-page p { margin: 0; }
.fleet-fields { display: flex; align-items: end; flex-wrap: wrap; gap: 10px; }
.fleet-fields label { display: grid; gap: 5px; color: #606266; font-size: 13px; }
.fleet-fields input, .fleet-fields select { border: 1px solid #dcdfe6; border-radius: 4px; padding: 6px; }
.fleet-fields input[type=number] { max-width: 78px; }
</style>

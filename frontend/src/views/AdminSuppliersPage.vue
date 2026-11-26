<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminError, adminResources } from '../api/adminResources'
import { useAdminQuery } from '../composables/useAdminQuery'
import { supplierKindLabels, type Supplier, type SupplierFields, type SupplierKind, type SupplierStatus } from '../types/adminResources'

const page = ref(1)
const filters = reactive({ name: '', status: '' as SupplierStatus | '' })
const { data, loading, error, load } = useAdminQuery(signal => adminResources.suppliers({
  ...filters, page: page.value, page_size: 20,
}, signal))

const dialog = ref(false)
const mode = ref<'create' | 'view' | 'edit'>('create')
const selectedId = ref('')
const saving = ref(false)
const formError = ref('')
const rowAction = ref('')
const blank: SupplierFields = {
  name: '', settlement_name: '', kind: 'other', fleet_city: '', contact_name: '', contact_info: '', notes: '',
}
const form = reactive<SupplierFields>({ ...blank })
const record = useAdminQuery(signal => adminResources.supplier(selectedId.value, signal))
const { data: details, loading: detailLoading, error: detailError } = record

function search() {
  page.value = 1
  void load()
}

function create() {
  record.clear()
  selectedId.value = ''
  Object.assign(form, blank)
  mode.value = 'create'
  formError.value = ''
  dialog.value = true
}

function fillForm(supplier: Supplier) {
  Object.assign(form, {
    name: supplier.name,
    settlement_name: supplier.settlement_name,
    kind: supplier.kind ?? 'other',
    fleet_city: supplier.fleet_city ?? '',
    contact_name: supplier.contact_name,
    contact_info: supplier.contact_info,
    notes: supplier.notes,
  })
}

async function loadRecord() {
  await record.load()
  if (details.value) fillForm(details.value)
}

function openRecord(id: string, nextMode: 'view' | 'edit') {
  record.clear()
  selectedId.value = id
  mode.value = nextMode
  formError.value = ''
  dialog.value = true
  void loadRecord()
}

async function save() {
  if (saving.value) return
  formError.value = ''
  if (!form.name.trim() || !form.settlement_name.trim()) {
    formError.value = '请填写供应商名称和结算主体。'
    return
  }
  saving.value = true
  try {
    if (mode.value === 'create') await adminResources.createSupplier(form)
    else await adminResources.updateSupplier(selectedId.value, form)
    dialog.value = false
    ElMessage.success('供应商已保存')
    await load()
  } catch (failure) {
    formError.value = adminError(failure)
  } finally {
    saving.value = false
  }
}

async function changeStatus(supplier: Supplier) {
  const disabling = supplier.status === 'active'
  if (disabling) {
    const confirmed = await ElMessageBox.confirm(
      '停用后，该供应商名下所有商品的报价将暂时不可售。', '停用供应商',
      { type: 'warning', confirmButtonText: '停用', cancelButtonText: '取消' },
    ).then(() => true, () => false)
    if (!confirmed) return
  }
  rowAction.value = supplier.id
  try {
    await adminResources.updateSupplier(supplier.id, { status: disabling ? 'inactive' : 'active' })
    ElMessage.success(disabling ? '供应商已停用' : '供应商已启用')
    await load()
  } catch (failure) {
    ElMessage.error(adminError(failure))
  } finally {
    rowAction.value = ''
  }
}

async function remove(supplier: Supplier) {
  const confirmed = await ElMessageBox.confirm(
    `确定删除「${supplier.name}」？有关联商品时需要先处理商品。`, '删除供应商',
    { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
  ).then(() => true, () => false)
  if (!confirmed) return
  rowAction.value = supplier.id
  try {
    await adminResources.deleteSupplier(supplier.id)
    if (data.value?.items.length === 1 && page.value > 1) page.value--
    ElMessage.success('供应商已删除')
    await load()
  } catch (failure) {
    ElMessage.error(adminError(failure))
  } finally {
    rowAction.value = ''
  }
}

onMounted(load)
</script>

<template>
  <section class="resource-page">
    <header class="resource-titlebar">
      <h1>供应商管理</h1>
      <el-button type="primary" @click="create">新建供应商</el-button>
    </header>
    <div class="resource-panel">
      <form class="resource-toolbar" @submit.prevent="search">
        <el-input v-model="filters.name" aria-label="供应商名称筛选" placeholder="按供应商名称搜索" clearable />
        <el-select v-model="filters.status" aria-label="供应商状态筛选" placeholder="全部状态" clearable>
          <el-option label="启用" value="active" />
          <el-option label="停用" value="inactive" />
        </el-select>
        <el-button native-type="submit" :loading="loading">查询</el-button>
      </form>
      <div v-if="error" class="resource-stack">
        <el-alert :title="error" type="error" show-icon :closable="false" />
        <div><el-button @click="load">重试</el-button></div>
      </div>
      <el-table v-else v-loading="loading" class="resource-table" :data="data?.items ?? []"
        empty-text="暂无匹配的供应商" row-key="id">
        <el-table-column label="供应商" min-width="180">
          <template #default="{ row }">
            <el-button link type="primary" @click="openRecord(row.id, 'view')">{{ row.name }}</el-button>
          </template>
        </el-table-column>
        <el-table-column label="结算主体" prop="settlement_name" min-width="160" />
        <el-table-column label="类型" width="110">
          <template #default="{ row }">{{ supplierKindLabels[row.kind as SupplierKind] ?? '其他' }}</template>
        </el-table-column>
        <el-table-column label="联系人" prop="contact_name" min-width="100" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'">
              {{ row.status === 'active' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="240">
          <template #default="{ row }">
            <div class="resource-actions">
              <router-link class="resource-link" :to="{ name: 'admin-products', query: { supplier_id: row.id } }">
                查看商品
              </router-link>
              <el-button link type="primary" @click="openRecord(row.id, 'edit')">编辑</el-button>
              <el-button link :disabled="!!rowAction" @click="changeStatus(row)">
                {{ row.status === 'active' ? '停用' : '启用' }}
              </el-button>
              <el-button link type="danger" :disabled="!!rowAction" @click="remove(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="data && !error" class="resource-pagination">
        <el-pagination v-model:current-page="page" :page-size="20" :total="data.total"
          layout="total, prev, pager, next" @current-change="load" />
      </div>
    </div>

    <el-dialog v-model="dialog" class="resource-dialog" width="600px"
      :title="mode === 'create' ? '新建供应商' : mode === 'edit' ? '编辑供应商' : '供应商详情'"
      :before-close="(done: () => void) => { if (!saving) done() }" @closed="record.clear">
      <p v-if="detailLoading" role="status">正在加载供应商…</p>
      <div v-else-if="detailError" class="resource-stack">
        <el-alert :title="detailError" type="error" :closable="false" show-icon />
        <div><el-button @click="loadRecord">重试</el-button></div>
      </div>
      <el-descriptions v-else-if="mode === 'view' && details" :column="1" border>
        <el-descriptions-item label="供应商名称">{{ details.name }}</el-descriptions-item>
        <el-descriptions-item label="结算主体">{{ details.settlement_name }}</el-descriptions-item>
        <el-descriptions-item label="联系人">{{ details.contact_name || '—' }}</el-descriptions-item>
        <el-descriptions-item label="联系方式">{{ details.contact_info || '—' }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ details.status === 'active' ? '启用' : '停用' }}</el-descriptions-item>
        <el-descriptions-item label="备注">{{ details.notes || '—' }}</el-descriptions-item>
      </el-descriptions>
      <el-form v-else-if="mode !== 'view'" :model="form" label-position="top" @submit.prevent="save">
        <el-alert v-if="formError" :title="formError" class="resource-form-error"
          type="error" :closable="false" show-icon />
        <div class="resource-form-grid">
          <el-form-item label="供应商名称" required>
            <el-input v-model="form.name" maxlength="160" />
          </el-form-item>
          <el-form-item label="结算主体" required>
            <el-input v-model="form.settlement_name" maxlength="160">
              <template #append><el-button @click="form.settlement_name = form.name">同名</el-button></template>
            </el-input>
          </el-form-item>
          <el-form-item label="类型">
            <el-select v-model="form.kind" aria-label="供应商类型">
              <el-option v-for="(label, value) in supplierKindLabels" :key="value" :label="label" :value="value" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="form.kind === 'vehicle_fleet'" label="车队服务城市">
            <el-input v-model="form.fleet_city" placeholder="填写北京以启用试点" maxlength="100" />
          </el-form-item>
          <el-form-item label="联系人"><el-input v-model="form.contact_name" maxlength="100" /></el-form-item>
          <el-form-item label="联系方式"><el-input v-model="form.contact_info" maxlength="160" /></el-form-item>
          <el-form-item label="备注" class="resource-form-wide">
            <el-input v-model="form.notes" type="textarea" maxlength="4000" :rows="3" />
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button :disabled="saving" @click="dialog = false">{{ mode === 'view' ? '关闭' : '取消' }}</el-button>
        <el-button v-if="mode === 'view' && details && !detailLoading" type="primary" @click="mode = 'edit'">编辑</el-button>
        <el-button v-else-if="mode !== 'view' && !detailLoading && !detailError" type="primary" :loading="saving"
          @click="save">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

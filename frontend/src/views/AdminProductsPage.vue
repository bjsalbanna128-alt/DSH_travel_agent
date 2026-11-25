<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminError, adminResources } from '../api/adminResources'
import ResourceProductForm from '../components/ResourceProductForm.vue'
import ResourceSupplierSelect from '../components/ResourceSupplierSelect.vue'
import { useAdminQuery } from '../composables/useAdminQuery'
import { poiSourceLabels, productLabels, type Product, type ProductStatus, type ProductType } from '../types/adminResources'

const route = useRoute()
const router = useRouter()
const page = ref(1)
const filters = reactive({ name: '', supplier_id: '', type: '' as ProductType | '', status: '' as ProductStatus | '' })
const { data, loading, error, load } = useAdminQuery(signal => adminResources.products({
  ...filters, page: page.value, page_size: 20,
}, signal))
const editing = ref<Product | null>(null)
const formOpen = ref(false)
const rowAction = ref('')

watch(() => route.query.supplier_id, value => {
  filters.supplier_id = typeof value === 'string' ? value : ''
  page.value = 1
  void load()
}, { immediate: true })

async function search() {
  page.value = 1
  if ((route.query.supplier_id ?? '') !== filters.supplier_id) {
    await router.replace({ name: 'admin-products', query: { supplier_id: filters.supplier_id || undefined } })
  } else {
    await load()
  }
}

function openForm(product: Product | null = null) {
  editing.value = product
  formOpen.value = true
}

function refreshAfterSave() {
  formOpen.value = false
  void load()
}

async function changeStatus(product: Product) {
  const takingOffShelf = product.status === 'on_shelf'
  if (takingOffShelf) {
    const confirmed = await ElMessageBox.confirm(
      '下架后，该商品所有日期的报价将暂时不可售。', '商品下架',
      { type: 'warning', confirmButtonText: '下架', cancelButtonText: '取消' },
    ).then(() => true, () => false)
    if (!confirmed) return
  }
  rowAction.value = product.id
  try {
    await adminResources.updateProduct(product.id, { status: takingOffShelf ? 'off_shelf' : 'on_shelf' })
    ElMessage.success(takingOffShelf ? '商品已下架' : '商品已上架')
    await load()
  } catch (failure) {
    ElMessage.error(adminError(failure))
  } finally {
    rowAction.value = ''
  }
}

async function remove(product: Product) {
  const confirmed = await ElMessageBox.confirm(
    `确定删除「${product.name}」？有报价时需要先处理报价。`, '删除商品',
    { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
  ).then(() => true, () => false)
  if (!confirmed) return
  rowAction.value = product.id
  try {
    await adminResources.deleteProduct(product.id)
    if (data.value?.items.length === 1 && page.value > 1) page.value--
    ElMessage.success('商品已删除')
    await load()
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
      <h1>商品管理</h1>
      <el-button type="primary" @click="openForm()">新建商品</el-button>
    </header>
    <div class="resource-panel">
      <form class="resource-toolbar" @submit.prevent="search">
        <el-input v-model="filters.name" aria-label="商品名称筛选" placeholder="按商品名搜索" clearable />
        <ResourceSupplierSelect v-model="filters.supplier_id" clearable label="按供应商筛选" />
        <el-select v-model="filters.type" aria-label="按商品类型筛选" placeholder="全部类型" clearable value-on-clear="">
          <el-option v-for="(label, value) in productLabels" :key="value" :value="value" :label="label" />
        </el-select>
        <el-select v-model="filters.status" aria-label="按上下架状态筛选" placeholder="全部状态" clearable value-on-clear="">
          <el-option label="上架" value="on_shelf" />
          <el-option label="下架" value="off_shelf" />
        </el-select>
        <el-button native-type="submit" :loading="loading">查询</el-button>
      </form>
      <div v-if="error" class="resource-stack">
        <el-alert :title="error" type="error" show-icon :closable="false" />
        <div><el-button @click="load">重试</el-button></div>
      </div>
      <el-table v-else v-loading="loading" class="resource-table" :data="data?.items ?? []"
        empty-text="暂无匹配的商品" row-key="id">
        <el-table-column label="商品" min-width="160">
          <template #default="{ row }">
            <router-link class="resource-link" :to="{ name: 'admin-product-details', params: { id: row.id } }">
              {{ row.name }}
            </router-link>
          </template>
        </el-table-column>
        <el-table-column label="供应商" min-width="135">
          <template #default="{ row }">
            {{ row.supplier_name }}
            <el-tag v-if="row.supplier_status === 'inactive'" type="info" size="small">停用</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="104">
          <template #default="{ row }">{{ productLabels[(row as Product).type] }}</template>
        </el-table-column>
        <el-table-column label="POI" min-width="135">
          <template #default="{ row }">
            <template v-if="(row as Product).poi">
              {{ (row as Product).poi?.name }} <span class="resource-muted">{{ poiSourceLabels[(row as Product).poi!.source] }}</span>
            </template>
            <span v-else class="resource-muted">未绑定</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="78">
          <template #default="{ row }">
            <el-tag :type="row.status === 'on_shelf' ? 'success' : 'info'">{{ row.status === 'on_shelf' ? '上架' : '下架' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="报价" width="100">
          <template #default="{ row }">
            <router-link class="resource-link" :to="{ name: 'admin-product-details', params: { id: row.id } }">
              报价 {{ row.offer_count }} 条
            </router-link>
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="151">
          <template #default="{ row }">
            <div class="resource-actions">
              <el-button link type="primary" @click="openForm(row)">编辑</el-button>
              <el-button link :disabled="!!rowAction" @click="changeStatus(row)">
                {{ row.status === 'on_shelf' ? '下架' : '上架' }}
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
    <ResourceProductForm v-if="formOpen" :product="editing" :supplier-id="filters.supplier_id"
      @close="formOpen = false" @saved="refreshAfterSave" />
  </section>
</template>

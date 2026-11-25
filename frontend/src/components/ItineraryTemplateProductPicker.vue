<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { adminResources } from '../api/adminResources'
import { useAdminQuery } from '../composables/useAdminQuery'
import { productLabels, type Product, type ProductType } from '../types/adminResources'
import type { LinkedProduct } from '../types/itineraryTemplates'

const emit = defineEmits<{ close: []; choose: [product: LinkedProduct] }>()
const page = ref(1)
const filters = reactive({ name: '', type: '' as ProductType | '' })
const { data, loading, error, load } = useAdminQuery(signal => adminResources.products({
  ...filters, page: page.value, page_size: 10,
}, signal))

function search() {
  page.value = 1
  void load()
}

function choose(product: Product) {
  emit('choose', { id: product.id, name: product.name, type: product.type })
}

onMounted(load)
</script>

<template>
  <el-dialog :model-value="true" class="resource-dialog" width="720px" title="选择关联商品"
    @update:model-value="(open: boolean) => { if (!open) emit('close') }">
    <form class="resource-toolbar" @submit.prevent="search">
      <el-input v-model="filters.name" aria-label="关联商品名称筛选" placeholder="按商品名搜索" clearable />
      <el-select v-model="filters.type" aria-label="关联商品类型筛选" placeholder="全部商品类型" clearable value-on-clear="">
        <el-option v-for="(label, value) in productLabels" :key="value" :value="value" :label="label" />
      </el-select>
      <el-button native-type="submit" :loading="loading">查询</el-button>
    </form>
    <div v-if="error" class="resource-stack">
      <el-alert :title="error" type="error" :closable="false" show-icon />
      <div><el-button @click="load">重试</el-button></div>
    </div>
    <el-table v-else v-loading="loading" :data="data?.items ?? []" row-key="id" empty-text="暂无匹配的商品">
      <el-table-column prop="name" label="商品" min-width="160" />
      <el-table-column label="类型" min-width="100">
        <template #default="{ row }">{{ productLabels[(row as Product).type] }}</template>
      </el-table-column>
      <el-table-column label="状态" min-width="100">
        <template #default="{ row }">{{ row.supplier_status === 'inactive' ? '供应商停用' : row.status === 'on_shelf' ? '已上架' : '已下架' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="82">
        <template #default="{ row }"><el-button link type="primary" :aria-label="`选择 ${row.name}`" @click="choose(row)">选择</el-button></template>
      </el-table-column>
    </el-table>
    <div v-if="data && !error" class="resource-pagination">
      <el-pagination v-model:current-page="page" :page-size="10" :total="data.total"
        layout="total, prev, pager, next" @current-change="load" />
    </div>
    <template #footer><el-button @click="emit('close')">取消</el-button></template>
  </el-dialog>
</template>

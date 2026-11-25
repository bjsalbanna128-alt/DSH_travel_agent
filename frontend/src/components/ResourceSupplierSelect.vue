<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { adminResources } from '../api/adminResources'
import { useAdminQuery } from '../composables/useAdminQuery'

const id = defineModel<string>({ required: true })
const props = defineProps<{ disabled?: boolean; clearable?: boolean; label: string }>()
const keyword = ref('')
const list = useAdminQuery(signal => adminResources.suppliers({ name: keyword.value, page_size: 30 }, signal))
const selected = useAdminQuery(signal => adminResources.supplier(id.value, signal))
const { error, loading } = list
const options = computed(() => {
  const items = list.data.value?.items ?? []
  const current = selected.data.value
  return current?.id === id.value && !items.some(item => item.id === current.id)
    ? [current, ...items] : items
})

function search(value: string) {
  keyword.value = value
  void list.load()
}

watch(id, value => {
  selected.clear()
  if (value && !list.data.value?.items.some(item => item.id === value)) void selected.load()
}, { immediate: true })
onMounted(() => list.load())
</script>

<template>
  <el-select v-model="id" :aria-label="props.label" :placeholder="props.clearable ? '全部供应商' : '搜索并选择供应商'"
    :disabled="props.disabled" :clearable="props.clearable" value-on-clear="" filterable remote
    :remote-method="search" :loading="loading">
    <el-option v-for="supplier in options" :key="supplier.id" :value="supplier.id"
      :label="supplier.status === 'active' ? supplier.name : `${supplier.name}（停用）`" />
    <template #empty>
      <div v-if="error" class="supplier-select-error">
        {{ error }} <el-button link type="primary" @click="list.load">重试</el-button>
      </div>
      <p v-else class="supplier-select-error">没有匹配的供应商</p>
    </template>
  </el-select>
</template>

<style scoped>
.supplier-select-error { padding: 10px 15px; color: #5d6878; font-size: 13px; }
</style>

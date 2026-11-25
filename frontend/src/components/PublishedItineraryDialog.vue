<script setup lang="ts">
import { onMounted } from 'vue'
import { itineraryTemplates } from '../api/itineraryTemplates'
import { useAdminQuery } from '../composables/useAdminQuery'
import ItineraryTemplateContent from './ItineraryTemplateContent.vue'

const props = defineProps<{ id: string }>()
const emit = defineEmits<{ close: [] }>()
const { data, error, loading, load } = useAdminQuery(signal => itineraryTemplates.getPublished(props.id, signal))
onMounted(load)
</script>

<template>
  <el-dialog :model-value="true" class="resource-dialog" width="760px" title="查看线上版"
    @update:model-value="(open: boolean) => { if (!open) emit('close') }">
    <p v-if="loading" role="status">正在加载线上版…</p>
    <div v-else-if="error" class="resource-stack">
      <el-alert :title="error" type="error" show-icon :closable="false" />
      <div><el-button @click="load">重试</el-button></div>
    </div>
    <template v-else-if="data">
      <el-tag type="success" class="published-version">线上 v{{ data.version }}</el-tag>
      <ItineraryTemplateContent :content="data" />
    </template>
    <template #footer><el-button @click="emit('close')">关闭</el-button></template>
  </el-dialog>
</template>

<style scoped>
.published-version { margin-bottom: 12px; }
</style>

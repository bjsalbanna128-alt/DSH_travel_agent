<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminError } from '../api/adminResources'
import { itineraryTemplates } from '../api/itineraryTemplates'
import PublishedItineraryDialog from '../components/PublishedItineraryDialog.vue'
import { useAdminQuery } from '../composables/useAdminQuery'
import { templateLimits, visibilityLabels, type TemplateSummary, type TemplateVisibility } from '../types/itineraryTemplates'

const page = ref(1)
const filters = reactive({ title: '', destination: '', visibility: '' as TemplateVisibility | '' })
const { data, loading, error, load } = useAdminQuery(signal => itineraryTemplates.list({ ...filters, page: page.value }, signal))
const viewing = ref('')
const busy = ref(false)
const actionError = ref('')
const dateFormat = new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' })

function search() {
  page.value = 1
  actionError.value = ''
  void load()
}

function formatTime(value: string) {
  const date = new Date(/Z$|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`)
  return dateFormat.format(date)
}

async function unpublish(row: TemplateSummary) {
  busy.value = true
  actionError.value = ''
  try {
    const confirmed = await ElMessageBox.confirm(
      `下架「${row.title}」后，游客和 Agent 将无法再读取该模板。已保存的个人路书会保留原安排。`,
      '下架行程模板', { type: 'warning', confirmButtonText: '确认下架', cancelButtonText: '取消' },
    ).then(() => true, () => false)
    if (!confirmed) return
    await itineraryTemplates.unpublish(row.id, row.revision)
    ElMessage.success('模板已下架')
    await load()
  } catch (failure) {
    actionError.value = adminError(failure)
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="resource-page">
    <header class="resource-titlebar">
      <h1>行程模板</h1>
      <router-link :to="{ name: 'admin-itinerary-template-new' }" class="el-button el-button--primary">新建模板</router-link>
    </header>
    <div class="resource-panel">
      <form class="resource-toolbar" @submit.prevent="search">
        <el-input v-model="filters.title" :maxlength="templateLimits.title" aria-label="按草稿标题筛选" placeholder="草稿标题" clearable />
        <el-input v-model="filters.destination" :maxlength="templateLimits.destination" aria-label="按目的地筛选" placeholder="主要目的地" clearable />
        <el-select v-model="filters.visibility" aria-label="按可见性筛选" placeholder="全部状态" clearable value-on-clear="">
          <el-option v-for="(label, value) in visibilityLabels" :key="value" :label="label" :value="value" />
        </el-select>
        <el-button native-type="submit" :loading="loading">查询</el-button>
      </form>
      <div v-if="error || actionError" class="resource-stack template-list-error">
        <el-alert :title="error || actionError" type="error" show-icon :closable="false" />
        <div><el-button @click="search">重新加载列表</el-button></div>
      </div>
      <el-table v-if="!error" v-loading="loading" :data="data?.items ?? []" row-key="id" empty-text="暂无匹配的行程模板">
        <el-table-column label="草稿标题" min-width="168">
          <template #default="{ row }">
            <router-link class="resource-link" :to="{ name: 'admin-itinerary-template-edit', params: { id: row.id } }">{{ row.title }}</router-link>
          </template>
        </el-table-column>
        <el-table-column label="目的地" min-width="110">
          <template #default="{ row }">{{ row.destination || '—' }}</template>
        </el-table-column>
        <el-table-column label="天数" prop="days_count" width="70" />
        <el-table-column label="状态与版本" min-width="190">
          <template #default="{ row }">
            <div class="resource-actions">
              <el-tag :type="row.visibility === 'published' ? 'success' : 'info'">{{ visibilityLabels[(row as TemplateSummary).visibility] }}</el-tag>
              <span v-if="row.published_version" class="resource-muted">{{ row.visibility === 'published' ? '线上' : '最近发布' }} v{{ row.published_version }}</span>
              <el-tag v-if="row.has_unpublished_changes" type="warning">有草稿修改</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="最近更新" min-width="145">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" min-width="170">
          <template #default="{ row }">
            <div class="resource-actions">
              <router-link class="resource-link" :to="{ name: 'admin-itinerary-template-edit', params: { id: row.id } }">编辑</router-link>
              <template v-if="row.visibility === 'published'">
                <el-button link type="primary" @click="viewing = row.id">查看线上版</el-button>
                <el-button link type="danger" :disabled="busy" @click="unpublish(row)">下架</el-button>
              </template>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="data && !error" class="resource-pagination">
        <el-pagination v-model:current-page="page" :page-size="20" :total="data.total"
          layout="total, prev, pager, next" @current-change="load" />
      </div>
    </div>
    <PublishedItineraryDialog v-if="viewing" :id="viewing" @close="viewing = ''" />
  </section>
</template>

<style scoped>
.template-list-error { margin-bottom: 16px; }
</style>

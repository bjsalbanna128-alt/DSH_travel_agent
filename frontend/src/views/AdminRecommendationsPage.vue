<script setup lang="ts">
import { onMounted, reactive, ref, shallowRef } from 'vue'
import { ElMessage } from 'element-plus'
import { adminError, AdminRequestError } from '../api/adminResources'
import { adminRecommendations } from '../api/recommendations'
import RecommendationPreview from '../components/RecommendationPreview.vue'
import RecommendationThumbnail from '../components/RecommendationThumbnail.vue'
import { useAdminQuery } from '../composables/useAdminQuery'
import { visibilityLabels, type TemplateVisibility } from '../types/itineraryTemplates'
import type { RecommendationDraft } from '../types/recommendations'
import { confirmRecommendationRemoval } from '../utils/recommendationAdmin'

const page = ref(1)
const filters = reactive({ title: '', place: '', visibility: '' as TemplateVisibility | '' })
const { data, loading, error, load } = useAdminQuery(signal => adminRecommendations.list({ ...filters, page: page.value }, signal))
const preview = shallowRef<RecommendationDraft>()
const previewOpen = ref(false)
const busy = ref(false)
const actionError = ref('')
const editTarget = (id: string) => ({ name: 'admin-recommendation-edit', params: { id } })

function search() {
  page.value = 1
  actionError.value = ''
  void load()
}

function openPreview(row: RecommendationDraft) {
  preview.value = row
  previewOpen.value = true
}

async function changePublication(row: RecommendationDraft, publish: boolean) {
  busy.value = true
  actionError.value = ''
  try {
    if (!publish && !await confirmRecommendationRemoval(row.title)) return
    const perform = publish ? adminRecommendations.publish : adminRecommendations.unpublish
    const saved = await perform(row.id, row.revision)
    ElMessage.success(saved.message ?? '推荐已下架')
    await load()
  } catch (failure) {
    const issues = failure instanceof AdminRequestError ? failure.issues.map(issue => issue.message) : []
    actionError.value = [adminError(failure), ...issues].join(' ')
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="resource-page">
    <header class="resource-titlebar">
      <h1>推荐内容</h1>
      <router-link :to="{ name: 'admin-recommendation-new' }" class="el-button el-button--primary">新建推荐</router-link>
    </header>
    <div class="resource-panel">
      <form class="resource-toolbar" @submit.prevent="search">
        <el-input v-model="filters.title" :maxlength="40" aria-label="按草稿标题筛选" placeholder="草稿标题" clearable />
        <el-input v-model="filters.place" :maxlength="100" aria-label="按推荐地点筛选" placeholder="推荐地点" clearable />
        <el-select v-model="filters.visibility" aria-label="按发布状态筛选" placeholder="全部状态" clearable value-on-clear="">
          <el-option v-for="(label, value) in visibilityLabels" :key="value" :label="label" :value="value" />
        </el-select>
        <el-button native-type="submit" :loading="loading">查询</el-button>
      </form>
      <div v-if="error || actionError" class="resource-stack error-region">
        <el-alert :title="error || actionError" type="error" show-icon :closable="false" />
        <div><el-button @click="search">重新加载列表</el-button></div>
      </div>
      <el-table v-if="!error" v-loading="loading" :data="data?.items ?? []" row-key="id" empty-text="暂无匹配的推荐">
        <el-table-column label="封面" width="120">
          <template #default="{ row }"><RecommendationThumbnail :cover="row.cover" :title="row.title" :place="row.place" /></template>
        </el-table-column>
        <el-table-column label="草稿标题" min-width="160">
          <template #default="{ row }"><router-link class="resource-link" :to="editTarget(row.id)">{{ row.title }}</router-link></template>
        </el-table-column>
        <el-table-column label="推荐地点" min-width="110">
          <template #default="{ row }">{{ row.place || '—' }}</template>
        </el-table-column>
        <el-table-column label="草稿顺序" prop="display_order" width="92" />
        <el-table-column label="状态与版本" min-width="170">
          <template #default="{ row }">
            <div class="resource-actions">
              <el-tag :type="row.visibility === 'published' ? 'success' : 'info'">{{ visibilityLabels[(row as RecommendationDraft).visibility] }}</el-tag>
              <span v-if="row.published_version" class="resource-muted">{{ row.visibility === 'published' ? '线上' : '最近发布' }} v{{ row.published_version }}</span>
              <el-tag v-if="row.has_unpublished_changes" type="warning">有未发布修改</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="210">
          <template #default="{ row }">
            <div class="resource-actions">
              <router-link class="resource-link" :to="editTarget(row.id)">编辑</router-link>
              <el-button link type="primary" @click="openPreview(row)">预览</el-button>
              <el-button link type="primary" :disabled="busy" @click="changePublication(row, true)">发布</el-button>
              <el-button v-if="row.visibility === 'published'" link type="danger" :disabled="busy" @click="changePublication(row, false)">下架</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="data && !error" class="resource-pagination">
        <el-pagination v-model:current-page="page" :page-size="20" :total="data.total"
          layout="total, prev, pager, next" @current-change="load" />
      </div>
    </div>
    <el-dialog v-model="previewOpen" title="草稿预览" width="min(920px, calc(100% - 24px))" append-to-body destroy-on-close>
      <RecommendationPreview v-if="previewOpen && preview" :content="preview" :cover="preview.cover" />
    </el-dialog>
  </section>
</template>

<style scoped>
.error-region { margin-bottom: 16px; }
</style>

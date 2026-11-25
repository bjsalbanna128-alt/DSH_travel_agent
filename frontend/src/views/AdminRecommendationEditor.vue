<script setup lang="ts">
import { computed, onScopeDispose, ref, shallowRef, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter, type RouteLocationNormalized } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminError, AdminRequestError } from '../api/adminResources'
import { adminRecommendations } from '../api/recommendations'
import RecommendationPreview from '../components/RecommendationPreview.vue'
import { useAdminQuery } from '../composables/useAdminQuery'
import { visibilityLabels } from '../types/itineraryTemplates'
import type { RecommendationDraft, RecommendationFields } from '../types/recommendations'
import { confirmRecommendationRemoval } from '../utils/recommendationAdmin'

const route = useRoute()
const router = useRouter()
const item = shallowRef<RecommendationDraft>()
const initialFields = { title: '', place: '', short_text: '', display_order: 100 }
const fields = ref<RecommendationFields>({ ...initialFields })
const file = shallowRef<File>()
const busy = ref<'save' | 'cover' | 'publish' | 'unpublish' | ''>('')
const error = ref('')
const issues = ref<Record<string, string>>({})
const conflict = ref(false)
const textChanged = computed(() => Object.entries(fields.value).some(([name, value]) =>
  value !== (item.value ?? initialFields)[name as keyof RecommendationFields]))
const hasUnsaved = computed(() => textChanged.value || Boolean(file.value))
const routeId = computed(() => String(route.params.id ?? ''))
const { data: loaded, load, clear, loading, error: loadError } = useAdminQuery(signal => adminRecommendations.get(routeId.value, signal))

function adopt(saved?: RecommendationDraft) {
  item.value = saved
  fields.value = saved ? {
    title: saved.title, place: saved.place, short_text: saved.short_text, display_order: saved.display_order,
  } : { ...initialFields }
}

watch(routeId, id => {
  if (id && item.value?.id === id) return
  clear()
  adopt()
  file.value = undefined
  resetErrors()
  if (id) void load()
}, { immediate: true })
watch(loaded, saved => { if (saved && saved.id === routeId.value) adopt(saved) })

async function confirmDiscard() {
  if (!hasUnsaved.value && !busy.value) return true
  if (busy.value) return false
  return ElMessageBox.confirm('离开会丢失尚未保存的文字或待上传的文件。', '放弃当前编辑？', {
    type: 'warning', confirmButtonText: '放弃编辑', cancelButtonText: '继续编辑',
  }).then(() => true, () => false)
}
function mayNavigate(to: RouteLocationNormalized) {
  return (to.name === 'admin-recommendation-edit' && to.params.id === item.value?.id) || confirmDiscard()
}
onBeforeRouteLeave(mayNavigate)
onBeforeRouteUpdate(mayNavigate)

function guardUnload(event: BeforeUnloadEvent) {
  if (hasUnsaved.value || busy.value) {
    event.preventDefault()
    event.returnValue = ''
  }
}
window.addEventListener('beforeunload', guardUnload)
onScopeDispose(() => window.removeEventListener('beforeunload', guardUnload))

function resetErrors() {
  error.value = ''
  issues.value = {}
  conflict.value = false
}

function pickFile(event: Event) {
  const input = event.target as HTMLInputElement
  if (input.files?.length) {
    file.value = input.files[0]
    delete issues.value.cover
  }
  input.value = ''
}

function inputOrder(event: Event) {
  fields.value.display_order = (event.target as HTMLInputElement).valueAsNumber
}

async function persist() {
  if (item.value && !textChanged.value) return item.value
  const saved = item.value
    ? await adminRecommendations.save(item.value.id, item.value.revision, fields.value)
    : await adminRecommendations.create(fields.value)
  adopt(saved)
  if (!routeId.value) {
    await router.replace({ name: 'admin-recommendation-edit', params: { id: saved.id } })
  }
  return saved
}

async function upload(saved: RecommendationDraft, selected: File) {
  if (selected.size > 5 * 1024 * 1024) throw new Error('封面大小不能超过 5 MiB。')
  const updated = await adminRecommendations.upload(saved.id, saved.revision, selected)
  item.value = updated
  file.value = undefined
  return updated
}

async function perform(action: NonNullable<typeof busy.value>) {
  if (busy.value) return
  busy.value = action
  resetErrors()
  try {
    if (action === 'cover') {
      if (!item.value || !file.value) return
      await upload(item.value, file.value)
      ElMessage.success('封面已保存到草稿')
    } else if (action === 'unpublish') {
      const saved = item.value
      if (!saved || !await confirmRecommendationRemoval(saved.title)) return
      item.value = await adminRecommendations.unpublish(saved.id, saved.revision)
      ElMessage.success('推荐已下架')
    } else {
      let saved = await persist()
      if (action === 'publish') {
        if (file.value) saved = await upload(saved, file.value)
        item.value = await adminRecommendations.publish(saved.id, saved.revision)
      }
      ElMessage.success(item.value?.message ?? '草稿已保存')
    }
  } catch (failure) {
    error.value = adminError(failure)
    if (failure instanceof AdminRequestError) {
      conflict.value = failure.status === 409
      for (const issue of failure.issues) {
        const field = issue.path.at(-1)
        if (typeof field === 'string') issues.value[field] = issue.message
      }
    }
  } finally {
    busy.value = ''
  }
}

async function reloadDraft() {
  if (!await confirmDiscard()) return
  file.value = undefined
  resetErrors()
  await load()
}
</script>

<template>
  <section class="resource-page">
    <header class="resource-titlebar">
      <h1>{{ item ? '编辑推荐' : '新建推荐' }}</h1>
      <router-link class="resource-link" :to="{ name: 'admin-recommendations' }">返回推荐内容</router-link>
    </header>
    <div v-if="loadError" class="resource-panel resource-stack">
      <el-alert :title="loadError" type="error" :closable="false" show-icon />
      <div><el-button @click="reloadDraft">重试加载</el-button></div>
    </div>
    <p v-else-if="loading || (routeId && !item)" role="status">正在加载草稿…</p>
    <template v-else>
      <div class="resource-panel">
        <div v-if="item" class="resource-actions edit-status">
          <el-tag :type="item.visibility === 'published' ? 'success' : 'info'">{{ visibilityLabels[item.visibility] }}</el-tag>
          <span v-if="item.published_version">{{ item.visibility === 'published' ? '线上' : '最近发布' }} v{{ item.published_version }}</span>
          <el-tag v-if="item.has_unpublished_changes" type="warning">有未发布修改</el-tag>
        </div>
        <el-alert v-if="error" :title="error" class="resource-form-error" type="error" show-icon :closable="false" />
        <el-button v-if="conflict" class="edit-status" @click="reloadDraft">重新加载草稿</el-button>
        <el-form label-position="top" :disabled="Boolean(busy)" @submit.prevent="perform('save')">
          <div class="resource-form-grid">
            <el-form-item label="推荐标题" required :error="issues.title">
              <el-input v-model="fields.title" :maxlength="40" show-word-limit />
            </el-form-item>
            <el-form-item label="推荐地点" :error="issues.place">
              <el-input v-model="fields.place" :maxlength="100" />
            </el-form-item>
            <el-form-item label="推荐短文" class="resource-form-wide" :error="issues.short_text">
              <el-input v-model="fields.short_text" type="textarea" :rows="4" :maxlength="200" show-word-limit />
            </el-form-item>
            <el-form-item label="展示顺序" for="recommendation-order" :error="issues.display_order">
              <input id="recommendation-order" class="order-input" type="number" min="0" max="2147483647" step="1"
                :value="Number.isNaN(fields.display_order) ? '' : fields.display_order" @input="inputOrder"
                :disabled="Boolean(busy)">
            </el-form-item>
            <el-form-item label="封面" :error="issues.cover">
              <div v-if="item" class="resource-stack">
                <input aria-label="选择封面" type="file" accept="image/jpeg,image/png,image/webp"
                  :disabled="Boolean(busy)" @change="pickFile">
                <div v-if="file" class="resource-actions">
                  <span class="resource-muted">{{ file.name }}</span>
                  <el-button size="small" :loading="busy === 'cover'" @click="perform('cover')">上传封面</el-button>
                  <el-button size="small" link @click="file = undefined">取消选择</el-button>
                </div>
                <span class="resource-muted">JPEG、PNG 或 WebP 静态图，最多 5 MiB，建议比例 16:9。</span>
              </div>
              <span v-else class="resource-muted">保存标题创建草稿后，即可上传封面。</span>
            </el-form-item>
          </div>
          <div class="resource-actions">
            <el-button native-type="submit" :loading="busy === 'save'">保存草稿</el-button>
            <el-button type="primary" :loading="busy === 'publish'" @click="perform('publish')">发布</el-button>
            <el-button v-if="item?.visibility === 'published'" type="danger" plain
              :loading="busy === 'unpublish'" @click="perform('unpublish')">下架</el-button>
          </div>
        </el-form>
      </div>
      <div class="resource-panel">
        <h2>草稿预览</h2>
        <RecommendationPreview :content="fields" :cover="item?.cover ?? null" />
      </div>
    </template>
  </section>
</template>

<style scoped>
.edit-status { margin-bottom: 14px; }
input[type="file"] { max-width: 100%; font: inherit; }
.order-input {
  width: 140px; padding: 0 10px; height: 32px; font: inherit; color: var(--el-text-color-regular);
  border: 1px solid var(--el-border-color); border-radius: var(--el-border-radius-base);
}
.order-input:focus-visible { outline: 1px solid var(--el-color-primary); border-color: var(--el-color-primary); }
</style>

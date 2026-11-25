<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter, type RouteLocationNormalized } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { AdminRequestError, adminError, type ApiFieldIssue } from '../api/adminResources'
import { itineraryTemplates } from '../api/itineraryTemplates'
import ItineraryTemplateContent from '../components/ItineraryTemplateContent.vue'
import ItineraryTemplateProductPicker from '../components/ItineraryTemplateProductPicker.vue'
import PublishedItineraryDialog from '../components/PublishedItineraryDialog.vue'
import { useAdminQuery } from '../composables/useAdminQuery'
import { useAuthStore } from '../stores/auth'
import { productLabels } from '../types/adminResources'
import {
  activityLabels, templateLimits as limits, visibilityLabels, type ActivityDraft, type DayDraft,
  type LinkedProduct, type TemplateContent, type TemplateDetail, type TemplateDraft,
} from '../types/itineraryTemplates'

interface EditableActivity extends ActivityDraft { key: number }
interface EditableDay extends Omit<DayDraft, 'activities'> { key: number; activities: EditableActivity[] }

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const id = computed(() => typeof route.params.id === 'string' ? route.params.id : '')
const current = ref<TemplateDetail | null>(null)
const form = reactive<Omit<TemplateDraft, 'days'> & { days: EditableDay[] }>({
  title: '', destination: '', tags: [], description: '', tips: '', days: [],
})
const tag = ref('')
const products = ref(new Map<string, LinkedProduct>())
const selecting = ref<EditableActivity>()
const previewing = ref(false)
const viewingPublished = ref(false)
const busy = ref<'save' | 'publish' | ''>('')
const error = ref('')
const conflict = ref(false)
const issues = ref<ApiFieldIssue[]>([])
let key = 0

function draft(): TemplateDraft {
  return {
    title: form.title, destination: form.destination, tags: [...form.tags], description: form.description, tips: form.tips,
    days: form.days.map(day => ({
      theme: day.theme, notes: day.notes,
      activities: day.activities.map(activity => ({
        time: activity.time, name: activity.name, category: activity.category,
        description: activity.description, product_id: activity.product_id,
      })),
    })),
  }
}

const serialized = computed(() => JSON.stringify(draft()))
const saved = ref(serialized.value)
const dirty = computed(() => serialized.value !== saved.value || !!tag.value.trim())
const { data: fetched, loading, error: loadingError, load, clear } = useAdminQuery(signal => itineraryTemplates.get(id.value, signal))

function apply(record: TemplateDetail | null) {
  current.value = record
  const content = record?.draft
  Object.assign(form, {
    title: content?.title ?? '', destination: content?.destination ?? '', tags: [...(content?.tags ?? [])],
    description: content?.description ?? '', tips: content?.tips ?? '',
    days: (content?.days ?? []).map(day => ({
      ...day, key: ++key, activities: day.activities.map(activity => ({ ...activity, key: ++key })),
    })),
  })
  products.value = new Map(record?.linked_products.map(product => [product.id, product]))
  tag.value = ''
  saved.value = serialized.value
  error.value = ''
  issues.value = []
  conflict.value = false
}

async function fetchDraft() {
  await load()
  if (!loadingError.value && fetched.value?.id === id.value) apply(fetched.value)
}

watch(id, value => {
  if (value && current.value?.id === value) return
  clear()
  selecting.value = undefined
  previewing.value = false
  viewingPublished.value = false
  apply(null)
  if (value) void fetchDraft()
}, { immediate: true })

watch(serialized, () => {
  if (!conflict.value) error.value = ''
  issues.value = []
})

function addTag() {
  const value = tag.value.trim()
  if (!value) return true
  if (form.tags.length >= limits.tags) {
    error.value = `最多添加 ${limits.tags} 个人群标签。`
    return false
  }
  form.tags.push(value)
  tag.value = ''
  return true
}

function addDay() {
  if (form.days.length < limits.days) form.days.push({ key: ++key, theme: '', notes: '', activities: [] })
}

function addActivity(day: EditableDay) {
  if (day.activities.length < limits.activities) {
    day.activities.push({ key: ++key, time: '', name: '', category: null, description: '', product_id: null })
  }
}

function move<T>(items: T[], index: number, direction: number) {
  const target = index + direction
  if (target < 0 || target >= items.length) return
  const [item] = items.splice(index, 1)
  if (item !== undefined) items.splice(target, 0, item)
}

function choose(product: LinkedProduct) {
  if (!selecting.value) return
  products.value.set(product.id, product)
  selecting.value.product_id = product.id
  selecting.value = undefined
}

const preview = computed<TemplateContent>(() => ({
  ...draft(),
  days: form.days.map((day, index) => ({
    day: index + 1, theme: day.theme, notes: day.notes,
    activities: day.activities.map(activity => {
      const product = activity.product_id ? products.value.get(activity.product_id) ?? null : null
      return {
        time: activity.time, name: activity.name, category: activity.category, description: activity.description,
        product, missingProduct: !product ? activity.product_id ?? undefined : undefined,
      }
    }),
  })),
}))

const fieldLabels: Record<string, string> = {
  title: '标题', destination: '主要目的地', tags: '适用人群标签', description: '简介', tips: '行前提示',
  days: '每日计划', theme: '当日主题', notes: '当日备注', activities: '活动列表', name: '活动名称',
  time: '时段说明', category: '活动类别', product_id: '关联商品',
}

function issuePath(issue: ApiFieldIssue) {
  return issue.path.filter(part => part !== 'body' && part !== 'draft')
}

function issueLabel(issue: ApiFieldIssue) {
  const path = issuePath(issue)
  const day = typeof path[1] === 'number' && path[0] === 'days' ? `第 ${path[1] + 1} 天` : ''
  const activity = typeof path[3] === 'number' && path[2] === 'activities' ? `活动 ${path[3] + 1}` : ''
  const field = fieldLabels[String(path.at(-1))] ?? fieldLabels[String(path[0])] ?? '模板内容'
  return [day, activity, field].filter(Boolean).join(' · ')
}

function fieldError(...path: (string | number)[]) {
  return issues.value.find(issue => issuePath(issue).join('.') === path.join('.'))?.message
}

function findField(issue: ApiFieldIssue) {
  const path = issuePath(issue)
  const target = document.getElementById(`template-${path.join('-')}`)
    ?? document.getElementById(`template-${path[0]}`)
  target?.scrollIntoView({ block: 'center' })
  target?.querySelector<HTMLElement>('input, textarea, button')?.focus({ preventScroll: true })
}

function report(failure: unknown) {
  if (failure instanceof AdminRequestError) {
    issues.value = failure.issues
    conflict.value = failure.status === 409
    error.value = issues.value.length ? '请检查下方标出的字段。' : failure.message
  } else {
    error.value = adminError(failure)
  }
}

async function persist() {
  if (!addTag()) return null
  const content = draft()
  if (!content.title.trim()) {
    error.value = '请填写模板标题。'
    issues.value = [{ path: ['title'], message: error.value }]
    return null
  }
  const previous = current.value
  const record = previous
    ? await itineraryTemplates.save(previous.id, previous.revision, content)
    : await itineraryTemplates.create(content)
  if (!auth.isLoggedIn || auth.role !== 'operator') return null
  apply(record)
  if (!previous) await router.replace({ name: 'admin-itinerary-template-edit', params: { id: record.id } })
  return record
}

async function save() {
  if (busy.value || loading.value) return
  busy.value = 'save'
  error.value = ''
  issues.value = []
  try {
    if (await persist()) ElMessage.success('草稿已保存')
  } catch (failure) {
    report(failure)
  } finally {
    busy.value = ''
  }
}

async function publish() {
  if (busy.value || loading.value) return
  busy.value = 'publish'
  error.value = ''
  issues.value = []
  try {
    const record = !current.value || dirty.value ? await persist() : current.value
    if (!record) return
    const published = await itineraryTemplates.publish(record.id, record.revision)
    if (!auth.isLoggedIn || auth.role !== 'operator') return
    apply(published)
    ElMessage.success(published.message ?? `已发布 v${published.published_version}`)
  } catch (failure) {
    report(failure)
  } finally {
    busy.value = ''
  }
}

async function confirmDiscard() {
  if (!dirty.value) return true
  return ElMessageBox.confirm('你有未保存的修改，继续后将丢弃这些输入。', '未保存的修改', {
    type: 'warning', confirmButtonText: '丢弃修改', cancelButtonText: '继续编辑',
  }).then(() => true, () => false)
}

async function reload() {
  if (await confirmDiscard()) await fetchDraft()
}

function guard(to: RouteLocationNormalized) {
  if (to.name === 'login' || auth.role !== 'operator') return true
  if (to.name === 'admin-itinerary-template-edit' && to.params.id === current.value?.id) return true
  return busy.value ? false : confirmDiscard()
}

onBeforeRouteLeave(guard)
onBeforeRouteUpdate(guard)

function beforeUnload(event: BeforeUnloadEvent) {
  if (!dirty.value) return
  event.preventDefault()
  event.returnValue = ''
}

onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
</script>

<template>
  <section class="resource-page template-editor">
    <header class="resource-titlebar template-editor-header">
      <div class="resource-stack">
        <router-link :to="{ name: 'admin-itinerary-templates' }" class="resource-link">返回行程模板</router-link>
        <h1>{{ id ? '编辑行程模板' : '新建行程模板' }}</h1>
        <div v-if="current" class="resource-actions">
          <el-tag :type="current.visibility === 'published' ? 'success' : 'info'">{{ visibilityLabels[current.visibility] }}</el-tag>
          <span v-if="current.published_version" class="resource-muted">{{ current.visibility === 'published' ? '线上' : '最近发布' }} v{{ current.published_version }}</span>
          <el-tag v-if="current.has_unpublished_changes" type="warning">有草稿修改</el-tag>
          <span v-if="dirty" class="resource-muted">有未保存修改</span>
        </div>
      </div>
      <div v-if="!id || current" class="resource-actions">
        <el-button v-if="current?.visibility === 'published'" :disabled="!!busy" @click="viewingPublished = true">查看线上版</el-button>
        <el-button :disabled="!!busy || loading" @click="previewing = true">草稿预览</el-button>
        <el-button :loading="busy === 'save'" :disabled="busy === 'publish' || loading" @click="save">保存草稿</el-button>
        <el-button type="primary" :loading="busy === 'publish'" :disabled="busy === 'save' || loading" @click="publish">{{ dirty || !current ? '保存并发布' : '发布' }}</el-button>
      </div>
    </header>

    <div v-if="loadingError" class="resource-panel resource-stack">
      <el-alert :title="loadingError" type="error" show-icon :closable="false" />
      <div><el-button @click="reload">重试</el-button></div>
    </div>
    <p v-if="loading && !current" role="status">正在加载草稿…</p>
    <div v-if="error" class="resource-panel resource-stack">
      <el-alert :title="error" type="error" show-icon :closable="false" />
      <ul v-if="issues.length" class="template-issues">
        <li v-for="(issue, index) in issues" :key="index">
          <el-button link type="primary" @click="findField(issue)">{{ issueLabel(issue) }}</el-button>
          <span>{{ issue.message }}</span>
        </li>
      </ul>
      <div v-if="conflict && id"><el-button @click="reload">重新加载最新草稿</el-button></div>
    </div>

    <el-form v-if="!id || current" label-position="top" :disabled="!!busy || loading" @submit.prevent>
      <section class="resource-panel">
        <h2>基本资料</h2>
        <div class="resource-form-grid template-fields">
          <el-form-item id="template-title" label="模板标题" required :error="fieldError('title')">
            <el-input v-model="form.title" :maxlength="limits.title" />
          </el-form-item>
          <el-form-item id="template-destination" label="主要目的地" :error="fieldError('destination')">
            <el-input v-model="form.destination" :maxlength="limits.destination" />
          </el-form-item>
          <el-form-item id="template-tags" label="适用人群标签" class="resource-form-wide">
            <div class="resource-actions template-tags">
              <el-tag v-for="(item, index) in form.tags" :key="index" :closable="!busy" @close="form.tags.splice(index, 1)">{{ item }}</el-tag>
              <el-input v-model="tag" aria-label="添加适用人群标签" :maxlength="limits.tag" placeholder="例如亲子、老人" @keydown.enter.prevent="addTag" />
              <el-button :disabled="!tag.trim() || form.tags.length >= limits.tags" @click="addTag">添加标签</el-button>
            </div>
          </el-form-item>
          <el-form-item id="template-description" label="简介">
            <el-input v-model="form.description" type="textarea" :rows="3" :maxlength="limits.description" />
          </el-form-item>
          <el-form-item id="template-tips" label="行前提示">
            <el-input v-model="form.tips" type="textarea" :rows="3" :maxlength="limits.tips" />
          </el-form-item>
        </div>
      </section>

      <section id="template-days" class="resource-panel">
        <header class="resource-titlebar">
          <h2>每日计划 <span class="resource-muted">{{ form.days.length }} 天</span></h2>
          <el-button :disabled="form.days.length >= limits.days" @click="addDay">添加一天</el-button>
        </header>
        <el-empty v-if="!form.days.length" description="尚未添加日程" :image-size="65" />
        <div v-for="(day, dayIndex) in form.days" :key="day.key" class="template-day">
          <header class="resource-titlebar">
            <h3>第 {{ dayIndex + 1 }} 天</h3>
            <div class="resource-actions">
              <el-button link :disabled="dayIndex === 0" :aria-label="`上移第 ${dayIndex + 1} 天`" @click="move(form.days, dayIndex, -1)">上移</el-button>
              <el-button link :disabled="dayIndex === form.days.length - 1" :aria-label="`下移第 ${dayIndex + 1} 天`" @click="move(form.days, dayIndex, 1)">下移</el-button>
              <el-button link type="danger" :aria-label="`移除第 ${dayIndex + 1} 天`" @click="form.days.splice(dayIndex, 1)">移除</el-button>
            </div>
          </header>
          <div class="resource-form-grid">
            <el-form-item :id="`template-days-${dayIndex}-theme`" label="当日主题" :error="fieldError('days', dayIndex, 'theme')">
              <el-input v-model="day.theme" :aria-label="`第 ${dayIndex + 1} 天主题`" :maxlength="limits.theme" />
            </el-form-item>
            <el-form-item :id="`template-days-${dayIndex}-notes`" label="当日备注">
              <el-input v-model="day.notes" :aria-label="`第 ${dayIndex + 1} 天备注`" :maxlength="limits.notes" />
            </el-form-item>
          </div>
          <section :id="`template-days-${dayIndex}-activities`" class="resource-stack">
            <p v-if="fieldError('days', dayIndex, 'activities')" class="template-field-error">{{ fieldError('days', dayIndex, 'activities') }}</p>
            <div v-for="(activity, activityIndex) in day.activities" :key="activity.key" class="template-activity">
              <div class="resource-titlebar">
                <h4>活动 {{ activityIndex + 1 }}</h4>
                <div class="resource-actions">
                  <el-button link :disabled="activityIndex === 0" :aria-label="`上移第 ${dayIndex + 1} 天活动 ${activityIndex + 1}`" @click="move(day.activities, activityIndex, -1)">上移</el-button>
                  <el-button link :disabled="activityIndex === day.activities.length - 1" :aria-label="`下移第 ${dayIndex + 1} 天活动 ${activityIndex + 1}`" @click="move(day.activities, activityIndex, 1)">下移</el-button>
                  <el-button link type="danger" :aria-label="`移除第 ${dayIndex + 1} 天活动 ${activityIndex + 1}`" @click="day.activities.splice(activityIndex, 1)">移除</el-button>
                </div>
              </div>
              <div class="resource-form-grid">
                <el-form-item :id="`template-days-${dayIndex}-activities-${activityIndex}-name`" label="活动名称" :error="fieldError('days', dayIndex, 'activities', activityIndex, 'name')">
                  <el-input v-model="activity.name" :maxlength="limits.name" :aria-label="`第 ${dayIndex + 1} 天活动 ${activityIndex + 1} 名称`" />
                </el-form-item>
                <el-form-item :id="`template-days-${dayIndex}-activities-${activityIndex}-category`" label="活动类别" :error="fieldError('days', dayIndex, 'activities', activityIndex, 'category')">
                  <el-select v-model="activity.category" :aria-label="`第 ${dayIndex + 1} 天活动 ${activityIndex + 1} 类别`" placeholder="请选择" clearable :value-on-clear="null">
                    <el-option v-for="(label, value) in activityLabels" :key="value" :label="label" :value="value" />
                  </el-select>
                </el-form-item>
                <el-form-item :id="`template-days-${dayIndex}-activities-${activityIndex}-time`" label="时段说明">
                  <el-input v-model="activity.time" :maxlength="limits.time" placeholder="例如上午" />
                </el-form-item>
                <el-form-item :id="`template-days-${dayIndex}-activities-${activityIndex}-product_id`" label="关联商品" :error="fieldError('days', dayIndex, 'activities', activityIndex, 'product_id')">
                  <div class="resource-actions">
                    <template v-if="activity.product_id">
                      <span v-if="products.get(activity.product_id)">{{ products.get(activity.product_id)?.name }} · {{ productLabels[products.get(activity.product_id)!.type] }}</span>
                      <span v-else>商品不可用（{{ activity.product_id }}）</span>
                      <el-button link @click="activity.product_id = null">解除关联</el-button>
                    </template>
                    <el-button link type="primary" :aria-label="`为第 ${dayIndex + 1} 天活动 ${activityIndex + 1} 选择关联商品`" @click="selecting = activity">{{ activity.product_id ? '更换商品' : '选择商品' }}</el-button>
                  </div>
                </el-form-item>
                <el-form-item :id="`template-days-${dayIndex}-activities-${activityIndex}-description`" label="活动描述" class="resource-form-wide">
                  <el-input v-model="activity.description" type="textarea" :maxlength="limits.activityDescription" :rows="2" />
                </el-form-item>
              </div>
            </div>
            <div><el-button :disabled="day.activities.length >= limits.activities" :aria-label="`第 ${dayIndex + 1} 天添加活动`" @click="addActivity(day)">添加活动</el-button></div>
          </section>
        </div>
      </section>
    </el-form>

    <el-dialog v-model="previewing" class="resource-dialog" width="760px" title="草稿预览">
      <ItineraryTemplateContent :content="preview" />
      <template #footer><el-button @click="previewing = false">关闭</el-button></template>
    </el-dialog>
    <ItineraryTemplateProductPicker v-if="selecting" @close="selecting = undefined" @choose="choose" />
    <PublishedItineraryDialog v-if="viewingPublished && current" :id="current.id" @close="viewingPublished = false" />
  </section>
</template>

<style scoped>
.template-editor-header { flex-wrap: wrap; }
.template-editor-header .resource-stack { gap: 6px; }
.template-fields { margin-top: 14px; }
.template-tags .el-input { width: 170px; }
.template-day { border: 1px solid #dce4ee; border-radius: 8px; padding: 16px; }
.template-day + .template-day { margin-top: 14px; }
.template-day h3 { font-size: 16px; }
.template-activity { background: #f7f9fc; border-radius: 6px; padding: 12px; }
.template-day .resource-titlebar { margin-bottom: 10px; }
.template-activity :deep(.el-form-item:last-child) { margin-bottom: 0; }
.template-issues { padding-left: 18px; }
.template-issues li { overflow-wrap: anywhere; }
.template-field-error { color: #b33b34; }
</style>

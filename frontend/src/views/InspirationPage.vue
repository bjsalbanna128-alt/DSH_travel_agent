<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { itineraryTemplates } from '../api/itineraryTemplates'
import ItineraryTemplateContent from '../components/ItineraryTemplateContent.vue'
import { useAdminQuery } from '../composables/useAdminQuery'
import { useTravelStore } from '../stores/travel'
import type { PublishedTemplate, ReaderTemplateSummary } from '../types/itineraryTemplates'

const router = useRouter()
const store = useTravelStore()

const { data, loading, error, load } = useAdminQuery(signal =>
  itineraryTemplates.listPublished({ page_size: 20 }, signal))
const summaries = computed<ReaderTemplateSummary[]>(() => data.value?.items ?? [])

const current = ref<PublishedTemplate>()
const detailLoading = ref(false)
const detailError = ref('')
let detailRequest: AbortController | undefined

const formOpen = ref(false)
const form = reactive({ departureCity: '', adults: 1, children: 0, elderly: 0, budget: '' })
const formError = ref('')

function pickDifferent(excludeId?: string): ReaderTemplateSummary | undefined {
  const pool = summaries.value.filter(item => item.id !== excludeId)
  const candidates = pool.length ? pool : summaries.value
  if (!candidates.length) return undefined
  return candidates[Math.floor(Math.random() * candidates.length)]
}

async function show(summary?: ReaderTemplateSummary) {
  if (!summary) {
    current.value = undefined
    return
  }
  detailRequest?.abort()
  const request = new AbortController()
  detailRequest = request
  detailLoading.value = true
  detailError.value = ''
  try {
    const detail = await itineraryTemplates.getPublished(summary.id, request.signal)
    if (!request.signal.aborted) current.value = detail
  } catch (failure) {
    if (!request.signal.aborted) detailError.value = failure instanceof Error ? failure.message : '模板加载失败'
  } finally {
    if (!request.signal.aborted) detailLoading.value = false
  }
}

const hasChoice = computed(() => summaries.value.length > 1)

function shuffle() {
  void show(pickDifferent(current.value?.id))
}

function openForm() {
  formError.value = ''
  formOpen.value = true
}

function startPlanning() {
  if (!current.value) return
  const departureCity = form.departureCity.trim()
  if (!departureCity) {
    formError.value = '请填写出发城市'
    return
  }
  const template = current.value
  store.startPlanningWithRequest(
    `${template.destination}${template.days_count}天：${template.title}`,
    {
      destination: template.destination,
      days: template.days_count,
      preferences: template.tags,
      adults: Math.max(1, Number(form.adults) || 1),
      children: Math.max(0, Number(form.children) || 0),
      elderly: Math.max(0, Number(form.elderly) || 0),
      budget_total: Math.max(0, Number(form.budget) || 0),
      departure_city: departureCity,
    },
  )
  formOpen.value = false
  void router.push('/plan')
}

onMounted(async () => {
  await load()
  void show(pickDifferent())
})
</script>

<template>
  <section class="inspiration-page">
    <header class="inspiration-header">
      <el-button text @click="router.push('/')">← 返回聊天</el-button>
      <h1>随机旅行灵感</h1>
      <span class="inspiration-hint">从精选行程模板里挑一个，补充几条信息就能开始规划</span>
    </header>

    <div v-if="loading || detailLoading" class="inspiration-state" role="status">正在挑选模板…</div>

    <div v-else-if="error" class="inspiration-state">
      <el-alert :title="error" type="error" :closable="false" show-icon />
      <el-button @click="load().then(() => show(pickDifferent()))">重试</el-button>
    </div>

    <div v-else-if="!summaries.length" class="inspiration-state">
      <p>暂时还没有上线的行程模板。</p>
      <el-button @click="router.push('/')">回到聊天自己规划</el-button>
    </div>

    <template v-else>
      <div v-if="detailError" class="inspiration-state">
        <el-alert :title="detailError" type="error" :closable="false" show-icon />
        <el-button @click="shuffle">换一个</el-button>
      </div>

      <article v-else-if="current" class="inspiration-card">
        <ItineraryTemplateContent :content="current" />
      </article>

      <footer class="inspiration-actions">
        <el-button :disabled="!hasChoice" @click="shuffle">
          {{ hasChoice ? '不满意？换一个' : '暂时只有这一个模板' }}
        </el-button>
        <el-button type="primary" :disabled="!current" @click="openForm">确认模板</el-button>
      </footer>
    </template>

    <el-dialog v-model="formOpen" title="补充出行信息" width="460px">
      <el-form label-width="96px" @submit.prevent="startPlanning">
        <el-form-item label="出发城市" required>
          <el-input v-model="form.departureCity" placeholder="例如：北京" maxlength="50" clearable />
        </el-form-item>
        <el-form-item label="出行人数">
          <div class="inspiration-people">
            <el-input-number v-model="form.adults" :min="1" :max="20" controls-position="right" />
            <span>成人</span>
            <el-input-number v-model="form.children" :min="0" :max="20" controls-position="right" />
            <span>儿童</span>
            <el-input-number v-model="form.elderly" :min="0" :max="20" controls-position="right" />
            <span>老人</span>
          </div>
        </el-form-item>
        <el-form-item label="总预算">
          <el-input v-model="form.budget" placeholder="人民币，不填由系统估算" maxlength="12" />
        </el-form-item>
      </el-form>
      <p v-if="formError" class="inspiration-error">{{ formError }}</p>
      <p class="resource-muted">
        模板只提供目的地、天数与偏好主题；具体景点与用餐会由 AI 按这些条件重新挑选。
      </p>
      <template #footer>
        <el-button @click="formOpen = false">取消</el-button>
        <el-button type="primary" @click="startPlanning">开始规划</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.inspiration-page { max-width: 880px; margin: 0 auto; padding: 20px 16px 40px; }
.inspiration-header { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-bottom: 16px; }
.inspiration-header h1 { font-size: 22px; margin: 0; }
.inspiration-hint { font-size: 13px; color: #909399; }
.inspiration-state { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 60px 16px; color: #909399; }
.inspiration-card { background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.inspiration-actions { display: flex; justify-content: center; gap: 12px; margin-top: 20px; }
.inspiration-people { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 13px; color: #606266; }
.inspiration-error { color: #f56c6c; font-size: 13px; margin: 0 0 8px 96px; }
</style>


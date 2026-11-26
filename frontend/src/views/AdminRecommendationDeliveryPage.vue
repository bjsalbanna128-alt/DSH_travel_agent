<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { adminError } from '../api/adminResources'
import { aiOperation } from '../api/aiOperations'
import RecommendationThumbnail from '../components/RecommendationThumbnail.vue'
import type { PublishedRecommendation } from '../types/recommendations'

const base = '/home-recommendations'
const states = { content_unpublished: '内容已下架', paused: '已停投', scheduled: '未开始', ended: '已结束', active: '投放中' }
interface Option { id: string; title: string; display_order: number }
interface Delivery extends Option {
  enabled: boolean
  starts_at: string | null
  ends_at: string | null
  revision: number
  operator_name: string | null
  status: keyof typeof states
}
const deliveries = ref<Delivery[]>([])
const selectable = ref<Option[]>([])
const edit = ref<{ id: string; revision: number; enabled: boolean; starts: string; ends: string }>()
const selected = ref('')
const previewTime = ref('')
const cards = ref<PublishedRecommendation[]>()
const busy = ref(false)
const error = ref('')
const output = ref('')

function toBeijing(value: string | null) {
  return value ? new Date(Date.parse(value) + 8 * 3_600_000).toISOString().slice(0, 19) : ''
}
function withZone(value: string) { return value ? `${value}+08:00` : null }
function change(row: Delivery) {
  edit.value = { id: row.id, revision: row.revision, enabled: row.enabled, starts: toBeijing(row.starts_at), ends: toBeijing(row.ends_at) }
}
function start() {
  if (selected.value) edit.value = { id: selected.value, revision: 0, enabled: true, starts: '', ends: '' }
}
async function loadLists() {
  const [active, choices] = await Promise.all([
    aiOperation<Delivery[]>(base), aiOperation<Option[]>(`${base}/selectable`),
  ])
  deliveries.value = active
  selectable.value = choices
}
async function run(operation: () => Promise<void>) {
  busy.value = true
  error.value = ''
  output.value = ''
  try { await operation() }
  catch (cause) { error.value = adminError(cause) }
  finally { busy.value = false }
}
async function save() {
  const data = edit.value
  if (!data) return
  await run(async () => {
    await aiOperation(`${base}/${encodeURIComponent(data.id)}`, 'PUT', {
      expected_revision: data.revision, enabled: data.enabled, starts_at: withZone(data.starts), ends_at: withZone(data.ends),
    })
    edit.value = undefined
    selected.value = ''
    output.value = '投放已保存。'
    await loadLists()
    if (cards.value) await loadPreview()
  })
}
async function loadPreview() {
  const time = withZone(previewTime.value)
  const search = time ? `?${new URLSearchParams({ at: time })}` : ''
  cards.value = await aiOperation<PublishedRecommendation[]>(`${base}/preview${search}`)
}
onMounted(() => run(loadLists))
</script>

<template>
  <section class="resource-page" v-loading="busy">
    <header class="resource-titlebar">
      <h1>首页弹窗投放</h1>
      <router-link class="el-button" :to="{ name: 'admin-recommendations' }">管理内容与排序</router-link>
    </header>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
    <el-alert v-if="output" :title="output" type="success" show-icon :closable="false" />
    <div class="resource-panel">
      <p>首次发布的内容可在这里加入投放。下架后不展示，重新发布时沿用原投放设置。</p>
      <div class="delivery-toolbar">
        <el-select v-model="selected" placeholder="选择已发布内容" aria-label="选择已发布内容" style="width: 280px">
          <el-option v-for="item in selectable" :key="item.id" :label="item.title" :value="item.id" />
        </el-select>
        <el-button :disabled="!selected" type="primary" @click="start">新增投放</el-button>
        <el-button @click="run(loadLists)">刷新</el-button>
      </div>
      <el-form v-if="edit" class="delivery-editor" label-position="top" @submit.prevent="save">
        <el-form-item label="起止时间（北京时间）">
          <label>开始 <input v-model="edit.starts" type="datetime-local" step="1" aria-label="投放开始时间" /></label>
          <label>结束 <input v-model="edit.ends" type="datetime-local" step="1" aria-label="投放结束时间" /></label>
          <span>可留空，分别表示立即开始和长期有效。</span>
        </el-form-item>
        <el-checkbox v-model="edit.enabled">启用投放</el-checkbox>
        <el-button native-type="submit" type="primary">保存投放</el-button>
        <el-button @click="edit = undefined">取消</el-button>
      </el-form>
      <el-table :data="deliveries" row-key="id" empty-text="暂无投放">
        <el-table-column prop="title" label="标题" min-width="150" />
        <el-table-column prop="display_order" label="发布排序" width="95" />
        <el-table-column label="起止时间（北京时间）" min-width="200">
          <template #default="{ row }">
            <div>{{ toBeijing(row.starts_at).replace('T', ' ') || '立即开始' }}</div>
            <div>{{ toBeijing(row.ends_at).replace('T', ' ') || '长期有效' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }: { row: Delivery }">{{ states[row.status] }}</template>
        </el-table-column>
        <el-table-column label="操作人" min-width="105">
          <template #default="{ row }">{{ row.operator_name ?? '系统' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ row }"><el-button link type="primary" @click="change(row)">编辑</el-button></template>
        </el-table-column>
      </el-table>
    </div>
    <div class="resource-panel">
      <h2>轮播预览</h2>
      <form class="delivery-toolbar" @submit.prevent="run(loadPreview)">
        <label>北京时间 <input v-model="previewTime" type="datetime-local" step="1" /></label>
        <el-button native-type="submit">查看预览</el-button>
      </form>
      <p v-if="cards?.length === 0">该时刻没有投放中的卡片。</p>
      <ol v-if="cards?.length" class="delivery-preview">
        <li v-for="item in cards" :key="item.id">
          <div class="preview-card">
            <RecommendationThumbnail :cover="{ id: item.cover_url, url: item.cover_url }" :title="item.title" :place="item.place" />
            <div><strong>{{ item.title }}</strong><p>{{ item.place }} · {{ item.short_text }}</p></div>
          </div>
        </li>
      </ol>
    </div>
  </section>
</template>

<style scoped>
.delivery-toolbar, .preview-card { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.delivery-editor { padding: 12px; margin: 12px 0; background: #f3f6fb; }
.delivery-editor label { margin-right: 12px; }
.delivery-preview li { margin-block: 12px; }
.el-alert { margin-bottom: 12px; }
</style>

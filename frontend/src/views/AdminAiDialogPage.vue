<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { aiOperation } from '../api/aiOperations'
import { adminError } from '../api/adminResources'
import type { ClarifyResponse } from '../api/travel'

type Field = 'destination' | 'days' | 'travel_time' | 'budget_total' | 'pace'
type Pace = 'relaxed' | 'moderate' | 'intensive'
interface Config {
  introduction: string
  order: Field[]
  required: Field[]
  questions: Record<Field, string>
  default_budget: number | null
  default_pace: Pace | null
}
interface Snapshot {
  config: Config
  revision: number
  published_revision: number
  published_version: number
}
interface Trial extends ClarifyResponse {
  collected: Record<string, unknown>
  continuation: string
}
const names: Record<Field, string> = { destination: '目的地', days: '天数', travel_time: '出发日期', budget_total: '预算', pace: '节奏' }
const paces = { relaxed: '轻松', moderate: '适中', intensive: '紧凑' }
const snapshot = ref<Snapshot>()
const config = ref<Config>()
const busy = ref(false)
const error = ref('')
const notice = ref('')
const input = ref('')
const trial = ref<Trial>()
const exchanges = ref<{ query: string; message: string }[]>([])
const dirty = computed(() => JSON.stringify(config.value) !== JSON.stringify(snapshot.value?.config))

function clearTrial() {
  trial.value = undefined
  exchanges.value = []
  input.value = ''
}
function assign(value: Snapshot) {
  snapshot.value = value
  config.value = JSON.parse(JSON.stringify(value.config))
}
async function run(operation: () => Promise<void>) {
  busy.value = true
  error.value = ''
  notice.value = ''
  try { await operation() }
  catch (cause) { error.value = adminError(cause) }
  finally { busy.value = false }
}
function load() {
  return run(async () => {
    assign(await aiOperation<Snapshot>('/dialog-config'))
    clearTrial()
  })
}
function move(index: number, direction: number) {
  const order = config.value!.order
  const field = order[index]
  const other = order[index + direction]
  if (!field || !other) return
  order[index] = other
  order[index + direction] = field
}
function requireField(field: 'budget_total' | 'pace', enabled: boolean) {
  if (!config.value) return
  config.value.required = config.value.required.filter(entry => entry !== field)
  if (enabled) config.value.required.push(field)
  if (field === 'budget_total') config.value.default_budget = enabled ? null : 0
  else config.value.default_pace = enabled ? null : 'moderate'
}
function save() {
  return run(async () => {
    assign(await aiOperation<Snapshot>('/dialog-config/draft', 'PUT', {
      expected_revision: snapshot.value!.revision, config: config.value!,
    }))
    clearTrial()
    notice.value = '草稿已保存。'
  })
}
function publish() {
  return run(async () => {
    assign(await aiOperation<Snapshot>('/dialog-config/publish', 'POST', { expected_revision: snapshot.value!.revision }))
    notice.value = `已发布 v${snapshot.value!.published_version}。`
  })
}
function simulate() {
  const query = input.value.trim()
  if (!query || dirty.value) return
  return run(async () => {
    trial.value = await aiOperation<Trial>('/dialog-config/trial', 'POST', {
      query, expected_revision: snapshot.value!.revision, continuation: trial.value?.continuation,
    })
    exchanges.value.push({ query, message: trial.value.message })
    input.value = ''
  })
}
onMounted(load)
</script>

<template>
  <section class="dialog-page" v-loading="busy">
    <h1>对话配置</h1>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
    <el-alert v-if="notice" :title="notice" type="success" show-icon :closable="false" />
    <el-button v-if="!config" @click="load">重新加载</el-button>
    <template v-if="config && snapshot">
      <p>当前发布 v{{ snapshot.published_version }} · 草稿修订 {{ snapshot.revision }}</p>
      <el-form label-position="top">
        <el-form-item label="首轮引导语">
          <el-input v-model="config.introduction" type="textarea" maxlength="500" />
        </el-form-item>
        <el-form-item v-for="(field, index) in config.order" :key="field" :label="names[field]">
          <div class="dialog-question">
            <el-input v-model="config.questions[field]" :aria-label="`${names[field]}追问文案`" maxlength="300" />
            <el-button :disabled="index === 0" @click="move(index, -1)">上移</el-button>
            <el-button :disabled="index === config.order.length - 1" @click="move(index, 1)">下移</el-button>
          </div>
        </el-form-item>
        <el-form-item label="选填与默认值">
          <div class="dialog-options">
            <el-checkbox :model-value="config.required.includes('budget_total')" @change="(value: unknown) => requireField('budget_total', Boolean(value))">预算必问</el-checkbox>
            <el-input-number v-if="!config.required.includes('budget_total')" v-model="config.default_budget" :min="0" :precision="2" aria-label="默认预算，0 表示不限" />
            <span v-if="!config.required.includes('budget_total')">元（0 表示不限）</span>
          </div>
          <div class="dialog-options">
            <el-checkbox :model-value="config.required.includes('pace')" @change="(value: unknown) => requireField('pace', Boolean(value))">节奏必问</el-checkbox>
            <el-select v-if="!config.required.includes('pace')" v-model="config.default_pace" aria-label="默认节奏" style="width: 135px">
              <el-option v-for="(label, pace) in paces" :key="pace" :label="label" :value="pace" />
            </el-select>
          </div>
        </el-form-item>
        <el-button @click="load">重新加载</el-button>
        <el-button :disabled="!dirty" @click="save">保存草稿</el-button>
        <el-button type="primary" :disabled="dirty || snapshot.revision === snapshot.published_revision" @click="publish">发布</el-button>
      </el-form>
      <h2>模拟试聊</h2>
      <p v-if="dirty">保存草稿后可开始试聊。</p>
      <div v-for="(exchange, index) in exchanges" :key="index" class="trial-exchange">
        <p><strong>游客</strong> {{ exchange.query }}</p>
        <p><strong>回复</strong> {{ exchange.message }}</p>
      </div>
      <div v-if="trial">
        <p>下一个缺项 · {{ names[trial.missing_fields[0] as Field] ?? '无' }}</p>
        <p>规划状态 · {{ trial.action === 'ready' ? '已就绪' : '待补充' }}</p>
        <p>已收集字段</p>
        <ul>
          <li v-for="(value, field) in trial.collected" :key="field">{{ names[field as Field] ?? field }} · {{ field === 'budget_total' && value === 0 ? '不限' : paces[value as Pace] ?? value }}</li>
        </ul>
      </div>
      <el-form class="dialog-question" @submit.prevent="simulate">
        <el-input v-model="input" placeholder="输入游客需求" aria-label="试聊输入" />
        <el-button native-type="submit" :disabled="dirty || !input.trim()">发送</el-button>
        <el-button @click="clearTrial">清空</el-button>
      </el-form>
    </template>
  </section>
</template>

<style scoped>
.dialog-page { max-width: 860px; }
.dialog-question, .dialog-options { display: flex; align-items: center; gap: 8px; width: 100%; }
.trial-exchange { padding: 4px 12px; margin-bottom: 12px; background: #f3f6fb; white-space: pre-wrap; overflow-wrap: anywhere; }
.el-alert { margin-bottom: 12px; }
</style>


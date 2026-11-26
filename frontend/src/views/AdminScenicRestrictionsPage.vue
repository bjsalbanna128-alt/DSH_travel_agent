<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { adminError, adminQueryString, adminResources } from '../api/adminResources'
import { aiOperation } from '../api/aiOperations'
import { useAdminQuery } from '../composables/useAdminQuery'
import type { PageResult, PoiReference } from '../types/adminResources'
import { restrictionKinds, restrictionStates, type ScenicDraft, type ScenicRestriction } from '../types/scenicQuality'

const base = '/scenic-restrictions'
const page = ref(1)
const filters = reactive({ city: '', name: '', kind: '', visibility: '' })
const { data, loading, error, load } = useAdminQuery(() => aiOperation<PageResult<ScenicRestriction>>(
  `${base}${adminQueryString({ ...filters, page: page.value })}`,
))
const city = ref('')
const keyword = ref('')
const lookup = useAdminQuery(signal => adminResources.pois(city.value.trim(), keyword.value.trim(), 'attraction', signal))
const draft = ref<Omit<ScenicDraft, 'poi'> & { poi: PoiReference | null }>()
const editing = ref<ScenicRestriction>()
const editorOpen = ref(false)
const busy = ref(false)
const actionError = ref('')
const actionNotice = ref('')

function search() { page.value = 1; void load() }
function openEditor(row?: ScenicRestriction) {
  actionError.value = ''
  editing.value = row
  draft.value = row ? {
    poi: row.poi, kind: row.kind, starts_on: row.starts_on, ends_on: row.ends_on ?? '',
    description: row.description, source_note: row.source_note,
  } : { poi: null, kind: 'closure', starts_on: '', ends_on: '', description: '', source_note: '' }
  city.value = row?.poi.city ?? ''
  keyword.value = row?.poi.name ?? ''
  lookup.clear()
  editorOpen.value = true
}
async function run(operation: () => Promise<void>) {
  busy.value = true
  actionError.value = ''
  actionNotice.value = ''
  try { await operation() }
  catch (cause) { actionError.value = adminError(cause) }
  finally { busy.value = false }
}
function saveDraft() {
  const form = draft.value
  if (!form?.poi) return
  return run(async () => {
    const row = editing.value
    const payload = { ...form, ends_on: form.ends_on || null }
    if (row) await aiOperation(`${base}/${row.id}/draft`, 'PUT', { ...payload, expected_revision: row.revision })
    else await aiOperation(base, 'POST', payload)
    editorOpen.value = false
    actionNotice.value = '草稿已保存。'
    await load()
  })
}
function change(row: ScenicRestriction, action: 'publish' | 'disable') {
  return run(async () => {
    await aiOperation(`${base}/${row.id}/${action}`, 'POST', { expected_revision: row.revision })
    actionNotice.value = action === 'publish' ? '景区限制已发布。' : '景区限制已停用。'
    await load()
  })
}
async function remove(row: ScenicRestriction) {
  try { await ElMessageBox.confirm(`删除「${row.poi.name}」的限制草稿？`, '删除草稿', { type: 'warning' }) }
  catch { return }
  await run(async () => {
    await aiOperation(`${base}/${row.id}?expected_revision=${row.revision}`, 'DELETE')
    if (data.value?.items.length === 1 && page.value > 1) page.value--
    await load()
  })
}
onMounted(load)
</script>

<template>
  <section class="resource-page">
    <header class="resource-titlebar">
      <h1>景区限制</h1>
      <el-button type="primary" @click="openEditor()">新建限制</el-button>
    </header>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-alert v-if="actionError && !editorOpen" :title="actionError" type="error" :closable="false" />
    <el-alert v-if="actionNotice && !editorOpen" :title="actionNotice" type="success" :closable="false" />
    <div class="resource-panel">
      <el-form class="resource-toolbar" @submit.prevent="search">
        <el-input v-model="filters.city" aria-label="按城市筛选" placeholder="城市" clearable />
        <el-input v-model="filters.name" aria-label="按景区筛选" placeholder="景区名称" clearable />
        <el-select v-model="filters.kind" aria-label="按限制类型筛选" placeholder="全部类型" clearable value-on-clear="">
          <el-option v-for="(label, value) in restrictionKinds" :key="value" :label="label" :value="value" />
        </el-select>
        <el-select v-model="filters.visibility" aria-label="按发布状态筛选" placeholder="全部状态" clearable value-on-clear="">
          <el-option v-for="(label, value) in restrictionStates" :key="value" :label="label" :value="value" />
        </el-select>
        <el-button native-type="submit">查询</el-button>
      </el-form>
      <el-table v-loading="loading || busy" :data="data?.items ?? []" row-key="id" empty-text="暂无景区限制">
        <el-table-column prop="poi.city" label="城市" width="94" />
        <el-table-column prop="poi.name" label="景区" min-width="140" />
        <el-table-column label="类型" min-width="102">
          <template #default="{ row }: { row: ScenicRestriction }">{{ restrictionKinds[row.kind] }}</template>
        </el-table-column>
        <el-table-column label="适用日期（含首末日）" min-width="200">
          <template #default="{ row }">{{ row.starts_on }} 至 {{ row.ends_on || '长期' }}</template>
        </el-table-column>
        <el-table-column label="发布状态" min-width="160">
          <template #default="{ row }: { row: ScenicRestriction }">
            {{ restrictionStates[row.visibility] }}
            <span v-if="row.published_version"> · v{{ row.published_version }}</span>
            <small v-if="row.published_version && row.has_unpublished_changes"> · 有待发布修订</small>
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="205">
          <template #default="{ row }: { row: ScenicRestriction }">
            <el-button link type="primary" @click="openEditor(row)">编辑</el-button>
            <el-button v-if="row.visibility !== 'published' || row.has_unpublished_changes" link type="primary" @click="change(row, 'publish')">发布</el-button>
            <el-button v-if="row.visibility === 'published'" link type="warning" @click="change(row, 'disable')">停用</el-button>
            <el-button v-if="row.visibility === 'draft'" link type="danger" @click="remove(row)">删除草稿</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination v-model:current-page="page" :total="data?.total ?? 0" :page-size="20" layout="prev, pager, next, total" @current-change="load" />
    </div>
    <el-dialog v-model="editorOpen" :title="editing ? '编辑景区限制' : '新建景区限制'" width="min(700px, 96vw)" :close-on-click-modal="false">
      <el-alert v-if="actionError" :title="actionError" type="error" :closable="false" />
      <el-form v-if="draft" v-loading="busy" label-position="top" @submit.prevent="saveDraft">
        <el-form-item label="绑定景区 POI">
          <div class="poi-search">
            <el-input v-model="city" aria-label="POI 城市" placeholder="城市" maxlength="100" @keydown.enter.prevent="lookup.load()" />
            <el-input v-model="keyword" aria-label="POI 景区名称" placeholder="景区名称" maxlength="100" @keydown.enter.prevent="lookup.load()" />
            <el-button :disabled="!city.trim() || !keyword.trim()" :loading="lookup.loading.value" @click="lookup.load()">搜索 POI</el-button>
          </div>
          <p v-if="draft.poi" class="selected-poi">已选 {{ draft.poi.city }} · {{ draft.poi.name }}（{{ draft.poi.source }}）</p>
          <el-alert v-if="lookup.error.value || lookup.data.value?.warning" :title="lookup.error.value || lookup.data.value?.warning || ''" type="warning" :closable="false" />
          <el-table v-if="lookup.data.value" :data="lookup.data.value.items" size="small" max-height="180" empty-text="未找到匹配景点">
            <el-table-column prop="city" label="城市" />
            <el-table-column prop="name" label="景区" />
            <el-table-column prop="source" label="来源" />
            <el-table-column label="操作">
              <template #default="{ row }"><el-button link type="primary" :aria-label="`选择 ${row.name}`" @click="draft!.poi = row">选择</el-button></template>
            </el-table-column>
          </el-table>
        </el-form-item>
        <el-form-item label="限制类型">
          <el-select v-model="draft.kind" aria-label="限制类型">
            <el-option v-for="(label, value) in restrictionKinds" :key="value" :label="label" :value="value" />
          </el-select>
        </el-form-item>
        <el-form-item label="适用日期（北京时间，含首末日）">
          <label class="date-field">开始 <input v-model="draft.starts_on" type="date" required aria-label="限制开始日" /></label>
          <label>结束 <input v-model="draft.ends_on" type="date" :min="draft.starts_on" aria-label="限制结束日" /></label>
          <p class="selected-poi">结束日可留空，表示长期有效。</p>
        </el-form-item>
        <el-form-item label="限制说明">
          <el-input v-model="draft.description" aria-label="限制说明" type="textarea" maxlength="500" />
        </el-form-item>
        <el-form-item label="来源名称或公告链接">
          <el-input v-model="draft.source_note" aria-label="来源名称或公告链接" maxlength="300" />
        </el-form-item>
        <el-button native-type="submit" type="primary" :disabled="!draft.poi || !draft.starts_on || !draft.description.trim() || !draft.source_note.trim()">保存草稿</el-button>
        <el-button @click="editorOpen = false">取消</el-button>
      </el-form>
    </el-dialog>
  </section>
</template>

<style scoped>
.poi-search { display: flex; gap: 8px; width: 100%; }
.selected-poi { width: 100%; margin: 5px 0; }
.date-field { margin-right: 14px; }
.el-alert { margin-bottom: 10px; }
.el-pagination { margin-top: 12px; }
</style>

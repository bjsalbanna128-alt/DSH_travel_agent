<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminError } from '../api/adminResources'
import { contentsApi } from '../api/contents'
import { adminResources } from '../api/adminResources'
import { useAdminQuery } from '../composables/useAdminQuery'
import {
  contentKindLabels, contentStatusLabels, type ContentFields, type ContentKind, type ContentRecord,
  type ContentStatus,
} from '../types/contents'

const page = ref(1)
const filters = reactive({ kind: '' as ContentKind | '', city: '', status: '' as ContentStatus | '', keyword: '' })
const { data, loading, error, load } = useAdminQuery(signal =>
  contentsApi.list({ ...filters, page: page.value, page_size: 20 }, signal))

const dialog = ref(false)
const editingId = ref('')
const saving = ref(false)
const formError = ref('')
const blank = (): ContentFields => ({
  kind: 'attraction', city: '', name: '', category: '', rating: null, visit_duration_hours: null,
  opening_hours: '', ticket_price_hint_cny: null, star_rating: null, landmark_hint: '',
  lat: null, lng: null, tags: [], suitable_for: [], description: '', highlights: [], cover_image_url: '',
})
const form = reactive<ContentFields>(blank())

const binderOpen = ref(false)
const binderFor = ref<ContentRecord>()
const binderSelection = ref<string[]>([])
const productKeyword = ref('')
const productQuery = useAdminQuery(signal =>
  adminResources.products({ keyword: productKeyword.value, page: 1, page_size: 50 }, signal))
const { data: productPage, error: productsError, load: loadProducts } = productQuery

function search() {
  page.value = 1
  void load()
}

function openCreate() {
  editingId.value = ''
  Object.assign(form, blank())
  formError.value = ''
  dialog.value = true
}

function openEdit(row: ContentRecord) {
  editingId.value = row.id
  Object.assign(form, {
    kind: row.kind, city: row.city, name: row.name, category: row.category, rating: row.rating,
    visit_duration_hours: row.visit_duration_hours, opening_hours: row.opening_hours,
    ticket_price_hint_cny: row.ticket_price_hint_cny, star_rating: row.star_rating,
    landmark_hint: row.landmark_hint, lat: row.lat, lng: row.lng, tags: [...row.tags],
    suitable_for: [...row.suitable_for], description: row.description,
    highlights: [...row.highlights], cover_image_url: row.cover_image_url,
  })
  formError.value = ''
  dialog.value = true
}

function joinTags(list: string[]) {
  return list.join('、')
}

function splitTags(text: string) {
  return text.split(/[、,，\s]+/).map(item => item.trim()).filter(Boolean)
}

const locating = ref(false)

async function lookupCoordinates() {
  if (!form.name.trim()) {
    ElMessage.warning('请先填写名称，再查坐标。')
    return
  }
  locating.value = true
  try {
    const kind = form.kind === 'hotel' ? 'hotel' : 'attraction'
    const result = await adminResources.pois(form.city.trim(), form.name.trim(), kind)
    const hit = result.items.find(item => item.lat && item.lng)
    if (!hit) {
      ElMessage.warning('没有查到带坐标的结果，请手动填写。')
      return
    }
    form.lat = hit.lat as number
    form.lng = hit.lng as number
    ElMessage.success(`已填入「${hit.name}」的坐标`)
  } catch (failure) {
    ElMessage.error(adminError(failure))
  } finally {
    locating.value = false
  }
}

async function save() {  if (saving.value) return
  formError.value = ''
  if (!form.city.trim() || !form.name.trim()) {
    formError.value = '请填写城市与名称。'
    return
  }
  saving.value = true
  try {
    if (editingId.value) await contentsApi.update(editingId.value, form)
    else await contentsApi.create(form)
    dialog.value = false
    ElMessage.success('内容已保存')
    await load()
  } catch (failure) {
    formError.value = adminError(failure)
  } finally {
    saving.value = false
  }
}

async function toggleStatus(row: ContentRecord) {
  if (row.status === 'published') {
    try {
      await contentsApi.unpublish(row.id)
      ElMessage.success('已下架，同步向量后读者不再可见')
      await load()
    } catch (failure) {
      ElMessage.error(adminError(failure))
    }
    return
  }
  try {
    await contentsApi.publish(row.id)
    ElMessage.success('已上线，同步向量后可被检索')
    await load()
  } catch (failure) {
    // 发布被拒时直接打开编辑，把缺的字段摆在眼前。
    ElMessage.warning(adminError(failure))
    openEdit(row)
  }
}

async function remove(row: ContentRecord) {
  const confirmed = await ElMessageBox.confirm(
    `确定删除「${row.name}」？绑定商品的内容需要先解绑。`, '删除内容',
    { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
  ).then(() => true, () => false)
  if (!confirmed) return
  try {
    await contentsApi.remove(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (failure) {
    ElMessage.error(adminError(failure))
  }
}

function openBinder(row: ContentRecord) {
  binderFor.value = row
  binderSelection.value = row.products.map(product => product.id)
  binderOpen.value = true
  void loadProducts()
}

async function saveBindings() {
  if (!binderFor.value) return
  try {
    await contentsApi.bindProducts(binderFor.value.id, binderSelection.value)
    binderOpen.value = false
    ElMessage.success('绑定已保存')
    await load()
  } catch (failure) {
    ElMessage.error(adminError(failure))
  }
}

async function syncVectors(rebuild: boolean) {
  try {
    const result = await contentsApi.syncVectors(rebuild)
    ElMessage.success(`向量同步完成：新增 ${result.added}，更新 ${result.updated}，移除 ${result.removed}`)
  } catch (failure) {
    ElMessage.error(adminError(failure))
  }
}

onMounted(load)
</script>

<template>
  <section class="resource-page">
    <header class="resource-titlebar">
      <h1>景点与酒店内容</h1>
      <div class="resource-actions">
        <el-button @click="syncVectors(false)">同步向量（增量）</el-button>
        <el-button @click="syncVectors(true)">重建向量</el-button>
        <el-button type="primary" @click="openCreate">新建内容</el-button>
      </div>
    </header>
    <div class="resource-panel">
      <form class="resource-toolbar" @submit.prevent="search">
        <el-select v-model="filters.kind" placeholder="全部类型" clearable aria-label="类型筛选">
          <el-option v-for="(label, value) in contentKindLabels" :key="value" :label="label" :value="value" />
        </el-select>
        <el-input v-model="filters.city" placeholder="城市" maxlength="100" clearable />
        <el-input v-model="filters.keyword" placeholder="名称关键词" maxlength="160" clearable />
        <el-select v-model="filters.status" placeholder="全部状态" clearable aria-label="状态筛选">
          <el-option v-for="(label, value) in contentStatusLabels" :key="value" :label="label" :value="value" />
        </el-select>
        <el-button native-type="submit" :loading="loading">查询</el-button>
      </form>
      <div v-if="error" class="resource-stack">
        <el-alert :title="error" type="error" :closable="false" show-icon />
        <div><el-button @click="load">重试</el-button></div>
      </div>
      <el-table v-else v-loading="loading" class="resource-table" :data="data?.items ?? []"
        row-key="id" empty-text="暂无内容">
        <el-table-column label="名称" min-width="180">
          <template #default="{ row }">
            <strong>{{ row.name }}</strong>
            <div class="resource-muted">{{ contentKindLabels[row.kind as ContentKind] }} · {{ row.city }}</div>
          </template>
        </el-table-column>
        <el-table-column label="评分 / 参考价" min-width="130">
          <template #default="{ row }">
            <span>{{ row.rating ?? '—' }}</span>
            <div class="resource-muted">
              {{ row.ticket_price_hint_cny ? `¥${row.ticket_price_hint_cny}` : '无参考价' }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="绑定商品" min-width="170">
          <template #default="{ row }">
            <el-tag v-if="row.products.length" type="success" size="small">
              可售 {{ row.products.length }} 个
            </el-tag>
            <el-tag v-else type="info" size="small">未绑定</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'published' ? 'success' : row.status === 'draft' ? 'info' : 'warning'">
              {{ contentStatusLabels[row.status as ContentStatus] }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="240">
          <template #default="{ row }">
            <div class="resource-actions">
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button link @click="openBinder(row)">绑定商品</el-button>
              <el-button link @click="toggleStatus(row)">
                {{ row.status === 'published' ? '下架' : '发布' }}
              </el-button>
              <el-button link type="danger" @click="remove(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="data && data.total > 20" class="resource-pagination">
        <el-pagination v-model:current-page="page" :page-size="20" :total="data.total"
          layout="total, prev, pager, next" @current-change="load" />
      </div>
    </div>

    <el-dialog v-model="dialog" class="resource-dialog" width="720px"
      :title="editingId ? '编辑内容' : '新建内容'" :before-close="(done: () => void) => { if (!saving) done() }">
      <el-form :model="form" label-position="top" @submit.prevent="save">
        <el-alert v-if="formError" class="resource-form-error" :title="formError" type="error"
          :closable="false" show-icon />
        <div class="resource-form-grid">
          <el-form-item label="类型" required>
            <el-select v-model="form.kind" :disabled="!!editingId" aria-label="内容类型">
              <el-option v-for="(label, value) in contentKindLabels" :key="value" :label="label" :value="value" />
            </el-select>
          </el-form-item>
          <el-form-item label="城市" required><el-input v-model="form.city" maxlength="100" /></el-form-item>
          <el-form-item label="名称" required><el-input v-model="form.name" maxlength="160" /></el-form-item>
          <el-form-item v-if="form.kind === 'attraction'" label="分类">
            <el-input v-model="form.category" maxlength="32" placeholder="cultural / natural …" />
          </el-form-item>
          <el-form-item v-else label="星级">
            <el-input v-model.number="form.star_rating" inputmode="numeric" />
          </el-form-item>
          <el-form-item label="评分（0-5）"><el-input v-model.number="form.rating" inputmode="decimal" /></el-form-item>
          <el-form-item label="建议游玩（小时）">
            <el-input v-model.number="form.visit_duration_hours" inputmode="decimal" />
          </el-form-item>
          <el-form-item label="开放时间"><el-input v-model="form.opening_hours" maxlength="64" /></el-form-item>
          <el-form-item label="参考价（元）">
            <el-input v-model.number="form.ticket_price_hint_cny" inputmode="decimal"
              placeholder="仅展示，不代表售价" />
          </el-form-item>
          <el-form-item label="位置提示"><el-input v-model="form.landmark_hint" maxlength="160" /></el-form-item>
          <el-form-item label="纬度" required><el-input v-model.number="form.lat" inputmode="decimal" /></el-form-item>
          <el-form-item label="经度" required><el-input v-model.number="form.lng" inputmode="decimal" /></el-form-item>
          <el-form-item class="resource-form-wide" label="坐标获取">
            <div class="resource-actions">
              <el-button :loading="locating" @click="lookupCoordinates">按名称查坐标</el-button>
              <span class="resource-muted">用城市 + 名称查高德/本地 POI，查到后自动填入</span>
            </div>
          </el-form-item>
          <el-form-item class="resource-form-wide" label="标签（用、分隔）">
            <el-input :model-value="joinTags(form.tags)"
              @update:model-value="(value: string) => form.tags = splitTags(value)" />
          </el-form-item>
          <el-form-item class="resource-form-wide" label="适合人群（用、分隔）">
            <el-input :model-value="joinTags(form.suitable_for)"
              @update:model-value="(value: string) => form.suitable_for = splitTags(value)" />
          </el-form-item>
          <el-form-item class="resource-form-wide" label="介绍" required>
            <el-input v-model="form.description" type="textarea" :rows="4" maxlength="2000" />
            <span class="resource-muted">发布必填：城市、名称、介绍、纬度、经度。</span>
          </el-form-item>
          <el-form-item class="resource-form-wide" label="亮点（用、分隔）">
            <el-input :model-value="joinTags(form.highlights)"
              @update:model-value="(value: string) => form.highlights = splitTags(value)" />
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button :disabled="saving" @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="binderOpen" class="resource-dialog" width="620px"
      :title="`绑定商品 · ${binderFor?.name ?? ''}`">
      <p class="resource-muted">一个内容可绑定多个票种或房型；绑定后检索命中时会显示「可预订」。</p>
      <el-input v-model="productKeyword" placeholder="搜索商品名" clearable @change="loadProducts()" />
      <el-checkbox-group v-model="binderSelection" class="binder-list">
        <el-checkbox v-for="product in (productPage?.items ?? [])" :key="product.id"
          :value="product.id" :label="product.id" class="binder-item">
          {{ product.name }}（{{ product.type }} · {{ product.status === 'on_shelf' ? '在架' : '下架' }}）
        </el-checkbox>
      </el-checkbox-group>
      <el-alert v-if="productsError" :title="productsError" type="error" :closable="false" />
      <template #footer>
        <el-button @click="binderOpen = false">取消</el-button>
        <el-button type="primary" @click="saveBindings">保存绑定</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.binder-list { display: grid; gap: 6px; margin-top: 12px; max-height: 320px; overflow: auto; }
.binder-item { margin-right: 0; }
</style>



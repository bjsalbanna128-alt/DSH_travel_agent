<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { adminError, adminResources } from '../api/adminResources'
import { useAdminQuery } from '../composables/useAdminQuery'
import {
  poiSourceLabels, poiTypes, productLabels,
  type PoiReference, type Product, type ProductFields, type ProductType,
} from '../types/adminResources'
import ResourceSupplierSelect from './ResourceSupplierSelect.vue'

const props = defineProps<{ product: Product | null; supplierId: string }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const initial = props.product
const attrs = initial?.attributes
const form = reactive({
  name: initial?.name ?? '',
  supplier_id: initial?.supplier_id ?? props.supplierId,
  type: initial?.type ?? 'hotel_room' as ProductType,
  city: initial?.city ?? '',
  roomName: attrs && 'room_name' in attrs ? attrs.room_name : '',
  occupancy: attrs && 'occupancy' in attrs ? attrs.occupancy : 2 as number | undefined,
  breakfast: attrs && 'breakfast' in attrs ? attrs.breakfast : '',
  ticketName: attrs && 'ticket_name' in attrs ? attrs.ticket_name : '',
  audience: attrs && 'audience' in attrs ? attrs.audience : '',
  vehicleName: attrs && 'vehicle_name' in attrs ? attrs.vehicle_name : '',
  passengers: attrs && 'passenger_capacity' in attrs ? attrs.passenger_capacity : 4 as number | undefined,
})
const poi = ref<PoiReference | null>(initial?.poi ?? null)
const poiKeyword = ref('')
const formError = ref('')
const lookupValidation = ref('')
const saving = ref(false)
const identityLocked = computed(() => (initial?.offer_count ?? 0) > 0)
const bindingLocked = computed(() => identityLocked.value && initial?.status === 'on_shelf')

const { data: results, error: lookupError, loading: lookingUp, load: findPois, clear: clearLookup } =
  useAdminQuery(signal => adminResources.pois(form.city.trim(), poiKeyword.value.trim(), poiTypes[form.type], signal))

watch(() => form.type, (type) => {
  poi.value = type === initial?.type ? initial.poi : null
  clearLookup()
})
watch(() => form.city, clearLookup)
watch(poiKeyword, clearLookup)

function searchPoi() {
  lookupValidation.value = ''
  if (!form.city.trim() || !poiKeyword.value.trim()) {
    lookupValidation.value = '请填写城市和 POI 关键词。'
    return
  }
  void findPois()
}

function selectPoi(candidate: PoiReference) {
  poi.value = candidate
  clearLookup()
}

function productAttributes(): ProductFields['attributes'] {
  if (form.type === 'hotel_room') {
    if (!form.roomName.trim() || !form.occupancy || !form.breakfast.trim()) {
      throw new Error('请填写房型名、可住人数和早餐说明。')
    }
    return { room_name: form.roomName, occupancy: form.occupancy, breakfast: form.breakfast }
  }
  if (form.type === 'attraction_ticket') {
    if (!form.ticketName.trim() || !form.audience.trim()) throw new Error('请填写票种名和适用人群。')
    return { ticket_name: form.ticketName, audience: form.audience }
  }
  if (!form.vehicleName.trim() || !form.passengers) throw new Error('请填写车型名和可乘客数。')
  return { vehicle_name: form.vehicleName, passenger_capacity: form.passengers }
}

async function save() {
  if (saving.value) return
  formError.value = ''
  saving.value = true
  try {
    if (!form.name.trim() || !form.city.trim() || !form.supplier_id) {
      throw new Error('请填写商品名、城市并选择供应商。')
    }
    const data: ProductFields = {
      name: form.name, city: form.city, supplier_id: form.supplier_id, type: form.type,
      attributes: productAttributes(), poi: poi.value,
    }
    if (initial) await adminResources.updateProduct(initial.id, data)
    else await adminResources.createProduct(data)
    ElMessage.success('商品已保存')
    emit('saved')
  } catch (failure) {
    formError.value = adminError(failure)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-dialog :model-value="true" class="resource-dialog" width="700px" :title="initial ? '编辑商品' : '新建商品'"
    :before-close="(done: () => void) => { if (!saving) done() }"
    @update:model-value="(open: boolean) => { if (!open) emit('close') }">
    <el-form :model="form" label-position="top" @submit.prevent>
      <el-alert v-if="formError" class="resource-form-error" :title="formError" type="error"
        :closable="false" show-icon />
      <div class="resource-form-grid">
        <el-form-item label="商品名" required><el-input v-model="form.name" maxlength="160" /></el-form-item>
        <el-form-item label="供应商" required>
          <ResourceSupplierSelect v-model="form.supplier_id" label="商品供应商" :disabled="identityLocked" />
        </el-form-item>
        <el-form-item label="商品类型" required>
          <el-select v-model="form.type" aria-label="商品类型" :disabled="identityLocked">
            <el-option v-for="(label, value) in productLabels" :key="value" :value="value" :label="label" />
          </el-select>
        </el-form-item>
        <el-form-item label="城市" required><el-input v-model="form.city" maxlength="100" /></el-form-item>

        <template v-if="form.type === 'hotel_room'">
          <el-form-item label="房型名" required><el-input v-model="form.roomName" maxlength="160" /></el-form-item>
          <el-form-item label="可住人数" required><el-input-number v-model="form.occupancy" :min="1" :precision="0" /></el-form-item>
          <el-form-item label="早餐说明" required class="resource-form-wide">
            <el-input v-model="form.breakfast" placeholder="例如含双早、无早餐" maxlength="160" />
          </el-form-item>
        </template>
        <template v-else-if="form.type === 'attraction_ticket'">
          <el-form-item label="票种名" required><el-input v-model="form.ticketName" maxlength="160" /></el-form-item>
          <el-form-item label="适用人群" required><el-input v-model="form.audience" maxlength="160" /></el-form-item>
        </template>
        <template v-else>
          <el-form-item label="车型名" required><el-input v-model="form.vehicleName" maxlength="160" /></el-form-item>
          <el-form-item label="可乘客数" required><el-input-number v-model="form.passengers" :min="1" :precision="0" /></el-form-item>
        </template>
      </div>

      <section class="poi-picker" aria-label="POI 绑定">
        <div class="resource-actions">
          <strong>POI 绑定</strong>
          <template v-if="poi">
            <el-tag>{{ poi.name }} · {{ poiSourceLabels[poi.source] }}</el-tag>
            <el-button v-if="!bindingLocked" link @click="poi = null">取消绑定</el-button>
          </template>
          <span v-else class="resource-muted">未绑定</span>
        </div>
        <p v-if="bindingLocked" class="resource-muted">该商品已有报价，请下架后更换 POI。</p>
        <template v-else>
          <p class="resource-muted">{{ form.type === 'vehicle' ? '可选服务网点或接驳地点。' : '在商品上架前绑定对应地点。' }}</p>
          <div class="resource-actions">
            <el-input v-model="poiKeyword" aria-label="POI 关键词" maxlength="160" placeholder="按当前城市搜索地点"
              @keydown.enter.prevent="searchPoi" />
            <el-button :loading="lookingUp" @click="searchPoi">搜索 POI</el-button>
          </div>
          <div v-if="lookupError || lookupValidation" class="resource-stack">
            <el-alert :title="lookupError || lookupValidation" type="error" :closable="false" show-icon />
            <div v-if="lookupError"><el-button @click="searchPoi">重试 POI 查询</el-button></div>
          </div>
          <div v-if="results && !lookingUp && !lookupError" class="resource-stack">
            <el-alert v-if="results.warning" :title="results.warning" type="warning" :closable="false" show-icon />
            <p v-if="!results.items.length" class="resource-muted">没有匹配的 POI。</p>
            <ul v-else class="poi-results">
              <li v-for="candidate in results.items" :key="`${candidate.source}:${candidate.id}`">
                <div>{{ candidate.name }} <span class="resource-muted">{{ candidate.city }} · {{ poiSourceLabels[candidate.source] }}</span></div>
                <el-button link type="primary" :aria-label="`选择 ${candidate.name}`" @click="selectPoi(candidate)">选择</el-button>
              </li>
            </ul>
          </div>
        </template>
      </section>
    </el-form>
    <template #footer>
      <el-button :disabled="saving" @click="emit('close')">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.poi-picker { display: grid; gap: 10px; border-top: 1px solid #e4e8ef; padding-top: 15px; }
.poi-picker .el-input { flex: 1; min-width: 140px; }
.poi-results { list-style: none; max-height: 180px; overflow: auto; border: 1px solid #e4e8ef; border-radius: 6px; }
.poi-results li { display: flex; gap: 12px; align-items: center; justify-content: space-between; padding: 8px 12px; }
.poi-results li + li { border-top: 1px solid #e4e8ef; }
</style>

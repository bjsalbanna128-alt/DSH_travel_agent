<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { readYuan } from '../adminPricing'
import { AdminRequestError, adminError, adminResources } from '../api/adminResources'
import { useAdminQuery } from '../composables/useAdminQuery'
import type { OfferDay, OfferStatus } from '../types/adminResources'

const props = defineProps<{
  productId: string; priceUnit: string; mode: 'single' | 'batch'; day?: OfferDay;
}>()
const emit = defineEmits<{ close: []; saved: [] }>()
const existing = props.day?.quote
const form = reactive({
  date: props.day?.service_date ?? '', start: '', end: '',
  status: (existing?.status ?? '') as OfferStatus | '',
  cost: existing ? (existing.cost_fen / 100).toFixed(2) : '',
  sale: existing ? (existing.sale_fen / 100).toFixed(2) : '',
  overwrite: false,
})
const formError = ref('')
const previewError = ref('')
const serverConflicts = ref<string[]>()
const saving = ref(false)
const cost = computed(() => readYuan(form.cost))
const sale = computed(() => readYuan(form.sale))
const belowCost = computed(() => cost.value !== undefined && sale.value !== undefined && sale.value < cost.value)

const { data: preview, loading: previewing, error: loadError, load, clear } = useAdminQuery(signal =>
  adminResources.offers(props.productId, { start_date: form.start, end_date: form.end, page_size: 366 }, signal),
)
const conflicts = computed(() => serverConflicts.value ??
  preview.value?.items.filter(day => day.quote).map(day => day.service_date) ?? [],
)

watch(() => [form.start, form.end], () => {
  clear()
  previewError.value = ''
  serverConflicts.value = undefined
  form.overwrite = false
})

function previewBatch() {
  previewError.value = ''
  formError.value = ''
  serverConflicts.value = undefined
  form.overwrite = false
  if (!form.start || !form.end) {
    previewError.value = '请填写开始和结束日期。'
    return
  }
  void load()
}

async function save() {
  if (saving.value) return
  formError.value = ''
  if (cost.value === undefined || sale.value === undefined || !form.status) {
    formError.value = '请填写非负金额（最多两位小数、每项最多 ¥21474836.47），并选择报价状态。'
    return
  }
  if (props.mode === 'single' && !form.date) {
    formError.value = '请填写服务日期。'
    return
  }
  if (props.mode === 'batch' && (!preview.value || previewing.value || loadError.value)) {
    formError.value = '请先预览日期范围。'
    return
  }
  if (props.mode === 'batch' && conflicts.value.length && !form.overwrite) {
    formError.value = '所选日期存在报价，请调整日期或明确选择覆盖已有报价。'
    return
  }

  saving.value = true
  try {
    const values = { cost_fen: cost.value, sale_fen: sale.value, status: form.status }
    if (props.mode === 'batch') {
      const result = await adminResources.batchOffers(props.productId, {
        ...values, start_date: form.start, end_date: form.end, overwrite: form.overwrite,
      })
      ElMessage.success(`报价已保存，新增 ${result.created} 天，更新 ${result.updated} 天`)
    } else {
      if (existing) await adminResources.updateOffer(props.productId, form.date, values)
      else await adminResources.createOffer(props.productId, { ...values, service_date: form.date })
      ElMessage.success('报价已保存')
    }
    emit('saved')
  } catch (failure) {
    formError.value = adminError(failure)
    if (failure instanceof AdminRequestError && failure.dates.length) {
      if (props.mode === 'batch') serverConflicts.value = failure.dates
      else formError.value += ` ${failure.dates.join('、')}`
    }
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-dialog :model-value="true" class="resource-dialog" width="620px"
    :title="mode === 'batch' ? '批量填价' : existing ? '编辑报价' : '新增单日报价'"
    :before-close="(done: () => void) => { if (!saving) done() }"
    @update:model-value="(open: boolean) => { if (!open) emit('close') }">
    <el-form :model="form" label-position="top" @submit.prevent="save">
      <el-alert v-if="formError" class="resource-form-error" :title="formError" type="error"
        :closable="false" show-icon />
      <div class="resource-form-grid">
        <el-form-item v-if="mode === 'single'" label="服务日期" required class="resource-form-wide">
          <el-input v-model="form.date" type="date" :readonly="!!existing" />
        </el-form-item>
        <template v-else>
          <el-form-item label="开始日期" required><el-input v-model="form.start" type="date" /></el-form-item>
          <el-form-item label="结束日期（含当天）" required><el-input v-model="form.end" type="date" /></el-form-item>
          <div class="batch-preview resource-form-wide">
            <el-button :loading="previewing" @click="previewBatch">预览日期</el-button>
            <el-alert v-if="previewError || loadError" :title="previewError || loadError" type="error" :closable="false" />
            <template v-if="preview && !previewing && !loadError">
              <p>共 {{ preview.total }} 天，已有报价 {{ conflicts.length }} 天。</p>
              <template v-if="conflicts.length">
                <p class="batch-conflicts">冲突日期 {{ conflicts.join('、') }}</p>
                <el-checkbox v-model="form.overwrite">覆盖已有报价</el-checkbox>
              </template>
            </template>
          </div>
        </template>
        <el-form-item label="成本（元）" required><el-input v-model="form.cost" inputmode="decimal" placeholder="0.00" /></el-form-item>
        <el-form-item label="对客售价（元）" required><el-input v-model="form.sale" inputmode="decimal" placeholder="0.00" /></el-form-item>
        <el-alert v-if="belowCost" class="resource-form-wide resource-form-error" type="warning" :closable="false"
          show-icon title="售价低于成本，仍可保存为促销报价。" />
        <el-form-item label="报价状态" required>
          <el-select v-model="form.status" placeholder="请选择" aria-label="报价状态">
            <el-option label="可售" value="available" /><el-option label="停售" value="stopped" />
          </el-select>
        </el-form-item>
        <el-form-item label="计价单位"><span>人民币元 / {{ priceUnit }}</span></el-form-item>
      </div>
    </el-form>
    <template #footer>
      <el-button :disabled="saving" @click="emit('close')">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存报价</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.batch-preview { display: grid; gap: 8px; justify-items: start; margin-bottom: 16px; }
.batch-conflicts { max-height: 100px; overflow: auto; overflow-wrap: anywhere; }
</style>

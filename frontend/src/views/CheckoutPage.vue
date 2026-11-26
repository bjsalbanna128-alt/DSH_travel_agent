<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { adminError, AdminRequestError } from '../api/adminResources'
import { checkoutApi } from '../api/checkout'
import { ordersApi } from '../api/orders'
import { useAdminQuery } from '../composables/useAdminQuery'
import { formatFen, kindLabels, offerLabels, type CheckoutItem } from '../types/checkout'

const route = useRoute()
const router = useRouter()
const tripId = computed(() => String(route.params.tripId))
const departure = ref('')
const { data, loading, error, load, clear } = useAdminQuery(signal => checkoutApi.options(tripId.value, signal, departure.value))
const chosen = reactive<Record<string, number>>({})
const contact = reactive({ name: '', phone: '' })
const travelers = reactive([{ name: '', document_type: '身份证', document_number: '', phone: '' }])
const submitting = ref(false)
const conflict = ref<AdminRequestError>()
const conflictNames = ref<Record<string, string>>({})
const submitError = ref('')
let intent: { payload: string; key: string } | undefined

const selectedItems = computed(() => (data.value?.items ?? []).filter(item => item.sellable && quantity(item)))
const total = computed(() => selectedItems.value.reduce((sum, item) => sum + (item.unit_price_fen ?? 0) * quantity(item), 0))
const staleSelection = computed(() => Object.keys(chosen).some(key => chosen[key] && !selectedItems.value.some(item => item.key === key))
  || selectedItems.value.some(item => quantity(item) > limit(item)))
const canSubmit = computed(() => !loading.value && !error.value && !submitting.value && !staleSelection.value
  && Boolean(data.value?.departure_date) && selectedItems.value.length > 0)

function limit(item: CheckoutItem) { return Math.min(item.kind === 'hotel' ? 5 : 20, item.remaining ?? 0) }
function quantity(item: CheckoutItem) { return chosen[item.key] ?? 0 }
function changed(item: CheckoutItem) {
  return conflict.value?.conflicts.find(entry => item.product_id === entry.product_id
    && (!entry.service_date || item.days.some(day => day.service_date === entry.service_date)))
}
function toggle(item: CheckoutItem) {
  if (!item.sellable && !quantity(item)) return
  chosen[item.key] = quantity(item) ? 0 : item.quantity
  intent = undefined
}
function setQuantity(item: CheckoutItem, value: number) {
  chosen[item.key] = Math.max(1, Math.min(limit(item), value || 1))
  intent = undefined
}
function addTraveler() {
  travelers.push({ name: '', document_type: '身份证', document_number: '', phone: '' })
}
function renderGroup(kind: 'hotel' | 'ticket') {
  return (data.value?.items ?? []).filter(item => item.kind === kind)
}

async function submit() {
  if (!canSubmit.value) return
  if (!contact.name.trim() || !contact.phone.trim()) {
    ElMessage.warning('请填写联系人与联系电话。')
    return
  }
  const filled = travelers.filter(item => item.name.trim())
  if (!filled.length) {
    ElMessage.warning('请至少填写一位出行人。')
    return
  }
  submitting.value = true
  submitError.value = ''
  try {
    const selected = selectedItems.value.map(item => ({
      kind: item.kind, product_id: item.product_id,
      ...(item.kind === 'hotel' ? { check_in: item.check_in, check_out: item.check_out } : { service_date: item.service_date }),
      quantity: quantity(item),
      quotes: item.days.map(day => ({ service_date: day.service_date, token: day.token })),
    }))
    const payload = {
      contact_name: contact.name.trim(), contact_phone: contact.phone.trim(),
      trip_id: tripId.value, departure_date: data.value?.departure_date,
      travelers: filled, selected,
    }
    const encoded = JSON.stringify(payload)
    if (intent?.payload !== encoded) intent = { payload: encoded, key: crypto.randomUUID() }
    const order = await ordersApi.create(payload, intent.key)
    void router.push({ name: 'orders', query: { order: order.id } })
  } catch (failure) {
    submitError.value = adminError(failure)
    if (failure instanceof AdminRequestError && failure.status === 409 && failure.conflicts.length) {
      conflict.value = failure
      conflictNames.value = Object.fromEntries((data.value?.items ?? [])
        .filter(item => item.product_id).map(item => [item.product_id!, item.name]))
      intent = undefined
      await load()
      for (const key of Object.keys(chosen)) {
        if (!data.value?.items.some(item => item.key === key)) delete chosen[key]
      }
    }
  } finally {
    submitting.value = false
  }
}

watch(departure, () => {
  for (const key of Object.keys(chosen)) delete chosen[key]
  intent = undefined
  conflict.value = undefined
  submitError.value = ''
  void load()
}, { flush: 'sync' })
watch(tripId, () => {
  clear()
  if (departure.value) departure.value = ''
  else void load()
})
onMounted(load)
</script>

<template>
  <section class="checkout-page">
    <header class="checkout-header">
      <el-button text @click="router.back()">← 返回行程</el-button>
      <h1>选择要预订的项目</h1>
      <span class="checkout-meta">可以按需选购，免费路书随时可看。</span>
    </header>
    <label v-if="data?.date_selectable">
      出发日期 <input v-model="departure" type="date" aria-label="出发日期" :min="data.today" :disabled="submitting" />
    </label>
    <p v-else-if="data?.departure_date">出发日期 {{ data.departure_date }}</p>
    <p v-if="loading" role="status">正在核对价格与库存…</p>
    <el-alert v-else-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-alert v-if="submitError" :title="submitError" type="warning" :closable="false" show-icon />
    <ul v-if="conflict" class="checkout-breakdown">
      <li v-for="(entry, index) in conflict.conflicts" :key="index">
        {{ conflictNames[entry.product_id ?? ''] ?? '所选项目' }} {{ entry.service_date }} · {{ offerLabels[entry.reason] || '需重新确认' }}
      </li>
    </ul>
    <p v-if="!loading && data?.date_selectable && !data.departure_date">请选择出发日以查询价格和库存。</p>
    <p v-else-if="!loading && data && !data.sellable_count">
      {{ data.items.length ? '当前日期没有可订项目，请查看各项原因。' : '这份路书没有可预订的住宿或景点。' }}
    </p>
    <template v-if="data && !loading && !error">
      <section v-for="kind in (['hotel', 'ticket'] as const)" :key="kind">
        <template v-if="renderGroup(kind).length">
          <h2>{{ kindLabels[kind] }}</h2>
          <div v-for="item in renderGroup(kind)" :key="item.key" class="checkout-item">
            <el-checkbox :model-value="!!quantity(item)" :disabled="submitting || (!item.sellable && !quantity(item))"
              @change="toggle(item)">
              {{ item.place_name === item.name ? item.name : `${item.place_name} · ${item.name}` }}
            </el-checkbox>
            <span class="checkout-meta">{{ item.check_out ? `${item.check_in} 至 ${item.check_out}（退房）` : item.service_date || `第 ${item.days[0]?.day} 天` }}</span>
            <span v-if="item.unit_price_fen !== null" class="checkout-meta">{{ formatFen(item.unit_price_fen) }}{{ item.status === 'needs_date' ? ' 起（参考）' : !item.sellable ? '（参考）' : item.kind === 'hotel' ? ' / 间（全程）' : ' / 张' }}</span>
            <el-tag :type="item.sellable ? 'success' : 'info'" size="small">{{ offerLabels[item.status] }}{{ item.sellable ? ` · 余 ${item.remaining}` : '' }}</el-tag>
            <span v-if="item.status === 'reference'" class="checkout-meta">{{ item.reason === 'reference' ? '无当前可售绑定' : offerLabels[item.reason] }}</span>
            <el-tag v-if="changed(item)" type="warning" size="small">{{ offerLabels[changed(item)!.reason] || '报价已变化' }}</el-tag>
            <ul v-if="item.kind === 'hotel' && item.service_date" class="checkout-breakdown">
              <li v-for="day in item.days" :key="day.day">{{ day.service_date }} · {{ day.price_fen === null ? '无报价' : formatFen(day.price_fen) }}{{ day.reason !== 'sellable' ? ` · ${offerLabels[day.reason]}` : '' }}</li>
            </ul>
            <el-input-number v-if="item.sellable" :model-value="quantity(item) || item.quantity" :min="1" :max="limit(item)" size="small"
              :aria-label="`${item.name} 数量`" :disabled="submitting || !quantity(item)"
              @update:model-value="(value: number | undefined) => setQuantity(item, value ?? 1)" />
          </div>
        </template>
      </section>
      <section class="checkout-form">
        <h2>联系人与出行人</h2>
        <div class="checkout-grid">
          <el-input v-model="contact.name" placeholder="联系人姓名" maxlength="50" />
          <el-input v-model="contact.phone" placeholder="联系电话" maxlength="32" />
        </div>
        <div v-for="(traveler, index) in travelers" :key="index" class="checkout-grid">
          <el-input v-model="traveler.name" :placeholder="`出行人 ${index + 1}`" maxlength="50" />
          <el-input v-model="traveler.document_number" placeholder="证件号（选填，加密保存）" maxlength="64" />
          <el-input v-model="traveler.phone" placeholder="手机号" maxlength="32" />
        </div>
        <p class="checkout-meta">证件号用于记录本单出行资料，暂不核验。证件号码加密保存，运营仅可见脱敏号码。</p>
        <el-button text :disabled="travelers.length >= 20" @click="addTraveler">+ 添加出行人</el-button>
      </section>
      <footer class="checkout-footer">
        <span>已选 {{ selectedItems.length }} 项，合计 <strong>{{ formatFen(total) }}</strong></span>
        <span v-if="staleSelection">请调整不可售项目或超出库存的数量。</span>
        <el-button type="primary" :loading="submitting" :disabled="!canSubmit" @click="submit">确认报价并提交订单</el-button>
      </footer>
    </template>
  </section>
</template>

<style scoped>
.checkout-page { max-width: 900px; margin: 0 auto; padding: 20px 16px 40px; }
.checkout-header, .checkout-item, .checkout-footer { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.checkout-header { margin-bottom: 12px; }
.checkout-header h1 { margin: 0; font-size: 22px; }
.checkout-item { padding: 10px 0; border-bottom: 1px solid #ebeef5; }
.checkout-meta { color: #606266; font-size: 13px; }
.checkout-breakdown { margin: 0; font-size: 13px; }
.checkout-form { margin-top: 24px; }
.checkout-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 8px; }
.checkout-footer { justify-content: space-between; margin-top: 20px; }
</style>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, watch } from 'vue'
import { adminError } from '../api/adminResources'
import { checkoutApi } from '../api/checkout'
import { beijingTime, formatFen, offerLabels, vehicleLabels } from '../types/checkout'
import type { VehicleOffer, VehicleOrderSelection, VehicleQuote, VehicleSelection } from '../types/checkout'

const props = defineProps<{
  tripId: string
  departure: string | null
  offers: VehicleOffer[]
  people: number
  disabled: boolean
  conflicts: { service_key?: string; product_id?: string; service_date?: string; reason: string }[]
}>()
const emit = defineEmits<{ change: [items: VehicleOrderSelection[], blocking: boolean] }>()
interface Form {
  input: VehicleSelection
  checked: boolean
  product: string
  quote: VehicleQuote | null
  error: string
  busy: boolean
}
const forms = reactive<Record<string, Form>>({})
const pending = new Map<string, AbortController>()

function invalidate(key: string, message = '') {
  pending.get(key)?.abort()
  pending.delete(key)
  const form = forms[key]
  if (form) Object.assign(form, { quote: null, busy: false, error: message })
}

watch(() => props.tripId, () => {
  for (const key of Object.keys(forms)) {
    invalidate(key)
    delete forms[key]
  }
}, { flush: 'sync' })
watch(() => [props.tripId, props.offers] as const, () => {
  const current = new Set(props.offers.map(offer => offer.service_key))
  for (const key of Object.keys(forms)) {
    if (!current.has(key)) {
      invalidate(key)
      delete forms[key]
    }
  }
  for (const offer of props.offers) {
    forms[offer.service_key] ??= {
      input: { service_key: offer.service_key, start_time: offer.suggested_start, pickup: offer.pickup,
        dropoff: offer.dropoff, passengers: props.people, luggage: 0 },
      checked: false, product: '', quote: null, error: '', busy: false,
    }
  }
}, { immediate: true })
watch(() => props.departure, () => Object.keys(forms).forEach(key => invalidate(key)), { flush: 'sync' })
watch(() => props.conflicts, conflicts => {
  for (const conflict of conflicts) {
    if (conflict.service_key) invalidate(conflict.service_key, offerLabels[conflict.reason] || '请重新报价')
    else if (conflict.product_id) for (const [key, form] of Object.entries(forms)) {
      if (form.product === conflict.product_id && (!conflict.service_date || form.quote?.service_date === conflict.service_date)) {
        invalidate(key, offerLabels[conflict.reason] || '请重新报价')
      }
    }
  }
})
onBeforeUnmount(() => pending.forEach(controller => controller.abort()))

const selections = computed(() => {
  const items: VehicleOrderSelection[] = []
  let blocking = false
  for (const offer of props.offers) {
    const form = forms[offer.service_key]
    if (!form?.checked) continue
    const date = form.quote?.service_date
    const choice = form.quote?.options.find(entry => entry.product_id === form.product)
    if (!date || !choice?.token || choice.price_fen === null) {
      blocking = true
      continue
    }
    items.push({ kind: 'vehicle', product_id: choice.product_id, service_date: date, quantity: 1,
      quotes: [{ service_date: date, token: choice.token }], vehicle: { ...form.input }, price_fen: choice.price_fen })
  }
  return { items, blocking }
})
watch(selections, value => emit('change', value.items, value.blocking), { immediate: true, flush: 'sync' })

async function check(key: string, product?: string) {
  const form = forms[key]
  invalidate(key)
  if (!props.departure || !form?.checked) return
  const controller = new AbortController()
  pending.set(key, controller)
  form.busy = true
  try {
    const quote = await checkoutApi.vehicleQuote({
      ...form.input, start_time: form.input.start_time || null, trip_id: props.tripId,
      departure_date: props.departure, product_id: product || form.product || undefined,
    }, controller.signal)
    if (controller.signal.aborted) return
    const previous = product || form.product
    form.product = quote.options.some(choice => choice.sellable && choice.product_id === previous)
      ? previous : (quote.recommended_product_id || '')
    form.quote = quote
  } catch (failure) {
    if (!controller.signal.aborted) form.error = adminError(failure)
  } finally {
    if (pending.get(key) === controller) {
      pending.delete(key)
      form.busy = false
    }
  }
}

function toggle(key: string) {
  const form = forms[key]
  if (!form) return
  form.checked = !form.checked
  if (form.checked) void check(key)
  else invalidate(key)
}
</script>

<template>
  <section v-if="offers.length" class="vehicle-options">
    <h2>行程用车</h2>
    <article v-for="offer in offers" :key="offer.service_key" class="vehicle-option">
      <template v-if="forms[offer.service_key]">
        <el-checkbox :model-value="forms[offer.service_key]!.checked" :disabled="disabled" @change="toggle(offer.service_key)">
          第 {{ offer.day }} 天 · {{ offer.purpose === 'airport_transfer' ? '需要接机' : '选择全天包车' }}
        </el-checkbox>
        <el-tag v-if="offer.recommended" size="small">{{ offer.purpose === 'charter' ? '推荐包车' : '乘机到达' }}</el-tag>
        <p v-if="offer.legs.length" class="details">{{ [offer.legs[0]?.origin, ...offer.legs.map(leg => leg.destination)].join(' → ') }}</p>
        <template v-if="forms[offer.service_key]!.checked">
          <fieldset class="vehicle-fields" :disabled="disabled" @input.capture="invalidate(offer.service_key)">
            <label>上车时间（北京时间）
              <input v-model="forms[offer.service_key]!.input.start_time" type="time" required />
            </label>
            <label>乘客数
              <input v-model.number="forms[offer.service_key]!.input.passengers" type="number" min="1" max="500" required />
            </label>
            <label>行李件数
              <input v-model.number="forms[offer.service_key]!.input.luggage" type="number" min="0" max="500" required />
            </label>
            <template v-if="offer.purpose === 'airport_transfer'">
              <label>机场及航站楼
                <input v-model.trim="forms[offer.service_key]!.input.pickup" placeholder="如北京首都机场 T3" maxlength="160" />
              </label>
              <label>送达地点
                <input v-model.trim="forms[offer.service_key]!.input.dropoff" placeholder="行程酒店或北京市内地址" maxlength="160" />
              </label>
            </template>
          </fieldset>
          <p class="details">预计占用 {{ offer.duration_minutes / 60 }} 小时，每项按一趟计价。</p>
          <p v-if="forms[offer.service_key]!.quote?.starts_at && forms[offer.service_key]!.quote?.ends_at">
            北京时间 {{ beijingTime(forms[offer.service_key]!.quote!.starts_at!) }} 至 {{ beijingTime(forms[offer.service_key]!.quote!.ends_at!) }}
          </p>
          <p v-if="forms[offer.service_key]!.quote?.reason || forms[offer.service_key]!.error" role="status" class="quote-message">
            {{ forms[offer.service_key]!.error || offerLabels[forms[offer.service_key]!.quote!.reason!] }}
          </p>
          <fieldset v-if="forms[offer.service_key]!.quote?.options.length" class="vehicle-models" :disabled="disabled">
            <legend>{{ vehicleLabels[offer.purpose] }}车型</legend>
            <label v-for="choice in forms[offer.service_key]!.quote!.options" :key="choice.product_id">
              <input type="radio" :name="offer.service_key" :checked="forms[offer.service_key]!.product === choice.product_id"
                :disabled="!choice.sellable" @change="check(offer.service_key, choice.product_id)" />
              {{ choice.model_name }} · {{ choice.supplier_name }} · {{ choice.passenger_capacity }} 人／{{ choice.luggage_capacity }} 件
              <strong v-if="choice.price_fen !== null">{{ formatFen(choice.price_fen) }} / 趟</strong>
              <el-tag v-if="choice.product_id === forms[offer.service_key]!.quote?.recommended_product_id" size="small">推荐车型</el-tag>
              <span v-if="!choice.sellable" class="quote-message">{{ offerLabels[choice.reason] }}</span>
            </label>
          </fieldset>
          <el-button size="small" :disabled="disabled || !departure" :loading="forms[offer.service_key]!.busy" @click="check(offer.service_key)">
            核对用车报价
          </el-button>
        </template>
      </template>
    </article>
  </section>
</template>

<style scoped>
.vehicle-option { padding: 12px 0; border-bottom: 1px solid #ebeef5; }
.vehicle-fields { display: flex; flex-wrap: wrap; gap: 12px; padding: 12px 0 0; border: 0; margin: 0; }
.vehicle-fields label, .vehicle-models label { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.vehicle-fields input { min-width: 0; border: 1px solid #dcdfe6; border-radius: 4px; padding: 6px; }
.vehicle-fields input[type=number] { width: 64px; }
.details, .quote-message { font-size: 13px; color: #606266; }
.quote-message { color: #935209; }
.vehicle-models { border: 1px solid #ebeef5; border-radius: 6px; padding: 10px; margin: 0 0 12px; }
.vehicle-models label + label { margin-top: 8px; }
</style>

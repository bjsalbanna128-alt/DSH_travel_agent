<script setup lang="ts">
import { computed } from 'vue'
import { formatYuan, type ProductType } from '../api/dashboard'

const props = defineProps<{ items: { product_type: ProductType; amount_fen: number }[] }>()

const labels: Record<ProductType, string> = {
  hotel_room: '酒店',
  attraction_ticket: '门票',
  vehicle: '用车',
}
const order: ProductType[] = ['hotel_room', 'attraction_ticket', 'vehicle']

const rows = computed(() => {
  const amounts = new Map(props.items.map(item => [item.product_type, item.amount_fen]))
  const total = order.reduce((sum, key) => sum + (amounts.get(key) ?? 0), 0)
  return order.map(key => {
    const amount = amounts.get(key) ?? 0
    return {
      key, label: labels[key], amount,
      percent: total ? Math.round((amount / total) * 100) : 0,
    }
  })
})

const total = computed(() => rows.value.reduce((sum, row) => sum + row.amount, 0))

function width(amount: number): string {
  if (!total.value) return '0%'
  const percent = (amount / total.value) * 100
  return `${Math.max(percent, amount > 0 ? 2 : 0)}%`
}
</script>

<template>
  <div class="bars" role="img" aria-label="品类金额构成">
    <div v-for="row in rows" :key="row.key" class="bar-row">
      <span class="bar-label">{{ row.label }}</span>
      <div class="bar-track">
        <div class="bar-fill" :style="{ width: width(row.amount) }" />
      </div>
      <span class="bar-value">{{ formatYuan(row.amount) }}<small> · {{ row.percent }}%</small></span>
    </div>
  </div>
</template>

<style scoped>
.bars { display: flex; flex-direction: column; gap: 10px; }
.bar-row { display: grid; grid-template-columns: 44px minmax(0, 1fr) 150px; gap: 10px; align-items: center; }
.bar-label { color: #182940; font-weight: 600; font-size: .9rem; }
.bar-track { height: 14px; border-radius: 7px; background: #eef2f7; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 7px; background: linear-gradient(90deg, #255b90, #6b92b9); }
.bar-value { text-align: right; font-variant-numeric: tabular-nums; color: #182940; }
.bar-value small { color: #4a5e73; }
@media (max-width: 560px) {
  .bar-row { grid-template-columns: 40px minmax(0, 1fr); }
  .bar-value { grid-column: 1 / -1; text-align: left; }
}
</style>

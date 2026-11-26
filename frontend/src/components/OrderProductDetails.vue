<script setup lang="ts">
import { computed } from 'vue'
import { beijingTime, vehicleLabels } from '../types/checkout'
import type { VehicleLeg, VehiclePurpose } from '../types/checkout'
import type { OrderItemView } from '../types/orders'

const props = defineProps<{ item: OrderItemView }>()
const fleet = computed(() => props.item.attributes.fleet as {
  purpose: VehiclePurpose; model_name: string; starts_at: string; ends_at: string;
  pickup: string; dropoff: string; passengers: number; luggage: number; price_unit: string;
  legs?: VehicleLeg[];
} | undefined)
</script>

<template>
  <template v-if="fleet">
    <strong>{{ vehicleLabels[fleet.purpose] }} · {{ fleet.model_name }}</strong>
    <div>北京时间 {{ beijingTime(fleet.starts_at) }} 至 {{ beijingTime(fleet.ends_at) }}</div>
    <div v-if="fleet.legs?.length">{{ [fleet.legs[0]?.origin, ...fleet.legs.map(leg => leg.destination)].join(' → ') }}</div>
    <div v-else>{{ fleet.pickup }} → {{ fleet.dropoff }}</div>
    <div>{{ fleet.passengers }} 人 · {{ fleet.luggage }} 件行李 · 按{{ fleet.price_unit }}计价</div>
  </template>
  <template v-else>{{ item.product_name }}</template>
</template>

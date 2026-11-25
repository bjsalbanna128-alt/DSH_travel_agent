<script setup lang="ts">
import { memberTime, type PointOverview } from '../types/membership'

defineProps<{ points: PointOverview }>()
</script>

<template>
  <section class="resource-panel">
    <h2 class="support-section-title">积分概览</h2>
    <p class="member-balance"><strong>{{ points.effective_balance.toLocaleString() }}</strong> 有效积分</p>
    <h3 class="member-due-title">未来 30 天到期</h3>
    <p v-if="!points.expiring.length" class="resource-muted">未来 30 天没有积分到期。</p>
    <ul v-else class="member-expiry">
      <li v-for="lot in points.expiring" :key="lot.order_id">
        <span>订单 {{ lot.order_id }}</span>
        <span><strong>{{ lot.remaining_points.toLocaleString() }} 分</strong> · {{ memberTime(lot.expires_at) }}</span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.member-balance { display: flex; align-items: baseline; gap: 9px; color: #1c4c76; }
.member-balance strong { font-size: 2rem; }
.member-due-title { font-size: 1rem; margin: 14px 0 6px; }
.member-expiry { list-style: none; }
.member-expiry li { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; padding: 9px 0; overflow-wrap: anywhere; }
</style>

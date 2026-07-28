<script setup lang="ts">
import type { DayPlan } from '../types/travel'

defineProps<{
  dayPlans: DayPlan[]
  totalBudget: number
}>()

function formatPrice(v: number): string {
  return v > 0 ? `¥${v.toLocaleString()}` : '—'
}
</script>

<template>
  <div class="day-plan-list">
    <div v-if="totalBudget > 0" class="budget-bar">
      <span class="budget-label">预估总费用</span>
      <span class="budget-value">¥{{ totalBudget.toLocaleString() }}</span>
    </div>

    <el-collapse accordion>
      <el-collapse-item
        v-for="dp in dayPlans"
        :key="dp.day"
        :title="`Day ${dp.day}${dp.date ? ' — ' + dp.date : ''}`"
      >
        <div v-if="dp.attractions?.length" class="section">
          <div class="section-title">景点</div>
          <div v-for="a in dp.attractions" :key="a.id" class="item">
            <span class="item-name">{{ a.name }}</span>
            <span class="item-meta">{{ a.visit_duration_hours }}h · {{ formatPrice(a.ticket_price_cny) }}</span>
          </div>
        </div>

        <div v-if="dp.hotel" class="section">
          <div class="section-title">住宿</div>
          <div class="item">
            <span class="item-name">{{ dp.hotel.name }}</span>
            <span class="item-meta">¥{{ dp.hotel.price_per_night_cny }}/晚</span>
          </div>
        </div>

        <div v-if="dp.lunch || dp.dinner" class="section">
          <div class="section-title">餐饮</div>
          <div v-if="dp.lunch" class="item">
            <span class="item-name">午餐: {{ dp.lunch.name }}</span>
            <span class="item-meta">¥{{ dp.lunch.avg_price_per_person_cny }}/人</span>
          </div>
          <div v-if="dp.dinner" class="item">
            <span class="item-name">晚餐: {{ dp.dinner.name }}</span>
            <span class="item-meta">¥{{ dp.dinner.avg_price_per_person_cny }}/人</span>
          </div>
        </div>

        <div v-if="dp.notes" class="notes">{{ dp.notes }}</div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<style scoped>
.day-plan-list { margin-top: 8px; }
.budget-bar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px; background: #f0f9eb; border-radius: 8px; margin-bottom: 12px;
}
.budget-label { font-size: 14px; color: #606266; }
.budget-value { font-size: 20px; font-weight: 700; color: #67c23a; }
.section { margin-bottom: 8px; }
.section-title { font-size: 12px; color: #909399; margin-bottom: 4px; }
.item { display: flex; justify-content: space-between; align-items: center; padding: 4px 0; }
.item-name { font-size: 13px; color: #303133; }
.item-meta { font-size: 12px; color: #909399; }
.notes { font-size: 12px; color: #e6a23c; margin-top: 4px; }
</style>

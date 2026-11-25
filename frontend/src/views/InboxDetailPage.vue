<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { supportApi } from '../api/support'
import { useAdminQuery } from '../composables/useAdminQuery'
import { notificationDestination } from '../supportLinks'
import { supportTime } from '../types/support'

const route = useRoute()
const isOperatorView = computed(() => route.meta.area === 'b')
const { data, loading, error, load, clear } = useAdminQuery(signal =>
  supportApi.message(isOperatorView.value, String(route.params.id), signal))

watch(() => route.params.id, () => {
  clear()
  void load()
}, { immediate: true })

const travelersText = computed(() => {
  const travelers = data.value?.confirmation?.travelers
  if (!travelers) return ''
  const entries: Array<[string, number | undefined]> = [
    ['成人', travelers.adults], ['儿童', travelers.children], ['老人', travelers.elderly],
  ]
  return entries
    .filter(([, count]) => typeof count === 'number' && count > 0)
    .map(([label, count]) => `${label} ${count}`)
    .join(' · ')
})

const budgetText = computed(() => {
  const value = data.value?.confirmation?.total_budget_cny ?? 0
  return value > 0 ? `¥${value.toLocaleString()}` : '—'
})
</script>

<template>
  <section class="resource-page support-page">
    <header class="resource-titlebar support-title">
      <h1>{{ data?.confirmation ? '行程确认摘要' : '消息详情' }}</h1>
      <router-link :to="{ name: isOperatorView ? 'admin-messages' : 'messages' }" class="resource-link">返回我的消息</router-link>
    </header>
    <div v-if="error" class="resource-panel resource-stack">
      <el-alert :title="error" type="error" :closable="false" show-icon />
      <div><el-button :loading="loading" @click="load">重试</el-button></div>
    </div>
    <p v-else-if="loading && !data" role="status">正在加载消息…</p>
    <div v-else-if="data" class="resource-panel">
      <h2 class="support-section-title">{{ data.title }}</h2>
      <p class="support-copy">{{ data.body }}</p>
      <dl v-if="data.confirmation" class="support-meta">
        <div><dt>行程标题</dt><dd>{{ data.confirmation.title }}</dd></div>
        <div><dt>游客账号</dt><dd>{{ data.confirmation.username || '—' }}</dd></div>
        <div><dt>目的地</dt><dd>{{ data.confirmation.destination || '—' }}</dd></div>
        <div><dt>行程天数</dt><dd>{{ data.confirmation.duration_days }} 天</dd></div>
        <div v-if="travelersText" class="support-meta-wide"><dt>出行人数</dt><dd>{{ travelersText }}</dd></div>
        <div><dt>预估总费用</dt><dd>{{ budgetText }}</dd></div>
        <div><dt>确认版本</dt><dd>v{{ data.confirmation.version }}</dd></div>
        <div v-if="data.confirmation.modified_after_confirm"><dt>当前版本</dt>
          <dd>v{{ data.confirmation.current_version }}（确认后已有修改）</dd>
        </div>
        <div><dt>确认时间</dt><dd>{{ supportTime(data.confirmation.confirmed_at) }}</dd></div>
        <div class="support-meta-wide"><dt>行程 ID</dt><dd>{{ data.confirmation.trip_id }}</dd></div>
      </dl>
      <router-link v-else :to="notificationDestination(data)" class="resource-link open-ticket">查看工单</router-link>
      <router-link
        v-if="isOperatorView && data.confirmation"
        class="resource-link open-ticket"
        :to="{ name: 'admin-trip-detail', params: { id: data.confirmation.trip_id } }"
      >查看行程详情</router-link>
    </div>
  </section>
</template>

<style scoped>
.open-ticket { display: inline-block; margin-top: 12px; }
.support-meta-wide { grid-column: 1 / -1; }
</style>

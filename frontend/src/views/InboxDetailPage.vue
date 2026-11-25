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
        <div><dt>行程 ID</dt><dd>{{ data.confirmation.trip_id }}</dd></div>
        <div><dt>确认版本</dt><dd>v{{ data.confirmation.version }}</dd></div>
        <div><dt>确认时间</dt><dd>{{ supportTime(data.confirmation.confirmed_at) }}</dd></div>
      </dl>
      <router-link v-else :to="notificationDestination(data)" class="resource-link open-ticket">查看工单</router-link>
    </div>
  </section>
</template>

<style scoped>
.open-ticket { display: inline-block; margin-top: 12px; }
</style>

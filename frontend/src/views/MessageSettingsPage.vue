<script setup lang="ts">
import { onMounted, onScopeDispose, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminError } from '../api/adminResources'
import { supportApi } from '../api/support'
import { useAdminQuery } from '../composables/useAdminQuery'
import { supportTime, type MessageSetting } from '../types/support'

const { data, loading, error, load } = useAdminQuery(supportApi.settings)
const saving = ref('')
const actionError = ref('')
let mutation: AbortController | undefined
onMounted(load)
onScopeDispose(() => mutation?.abort())

async function setEnabled(row: MessageSetting, enabled: boolean) {
  if (saving.value || row.enabled === enabled) return
  actionError.value = ''
  saving.value = row.code
  const request = new AbortController()
  mutation = request
  try {
    const updated = await supportApi.setEnabled(row.code, row.revision, enabled, request.signal)
    if (request.signal.aborted) return
    if (data.value) data.value = data.value.map(item => item.code === row.code ? updated : item)
    ElMessage.success('通知配置已保存')
  } catch (failure) {
    if (request.signal.aborted) return
    actionError.value = adminError(failure)
    await load()
    if (error.value && !request.signal.aborted) actionError.value += ' 当前服务端状态暂时无法查询。'
  } finally {
    if (mutation === request) saving.value = ''
  }
}
</script>

<template>
  <section class="resource-page support-page">
    <header class="resource-titlebar support-title">
      <h1>消息配置</h1>
      <el-button :loading="loading" :disabled="Boolean(saving)" @click="load">刷新</el-button>
    </header>
    <div class="resource-panel">
      <p class="resource-muted support-section-title">开关应用于保存后发生的业务事件，已发送的消息会保留。</p>
      <el-alert v-if="actionError || error" class="support-error" :title="actionError || error"
        type="error" :closable="false" show-icon />
      <p v-if="loading && !data" role="status">正在加载消息配置…</p>
      <ul v-if="data" class="setting-list">
        <li v-for="row in data" :key="row.code">
          <div class="setting-header">
            <h2>{{ row.name }}</h2>
            <el-switch :model-value="row.enabled" :aria-label="row.name" active-text="开启" inactive-text="关闭"
              :loading="saving === row.code" :disabled="Boolean(saving) || loading"
              @update:model-value="setEnabled(row, $event === true)" />
          </div>
          <dl class="support-meta">
            <div><dt>触发时机</dt><dd>{{ row.trigger }}</dd></div>
            <div><dt>收件范围</dt><dd>{{ row.audience }}</dd></div>
            <div><dt>通道</dt><dd>站内消息</dd></div>
            <div><dt>最近修改</dt><dd>{{ row.updated_by_name ? `${row.updated_by_name} · ${supportTime(row.updated_at)}` : '系统默认' }}</dd></div>
          </dl>
        </li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.setting-list { list-style: none; }
.setting-list li { border-top: 1px solid #e4e8ef; padding: 15px 0; }
.setting-list li:last-child { padding-bottom: 0; }
.setting-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 9px; }
</style>

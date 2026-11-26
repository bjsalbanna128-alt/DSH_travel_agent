<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { adminError } from '../api/adminResources'
import { useInboxStore } from '../stores/inbox'
import { notificationDestination } from '../supportLinks'
import { supportTime, type InboxMessage } from '../types/support'

const inbox = useInboxStore()
const router = useRouter()
const route = useRoute()
const opening = ref('')
const actionError = ref('')

watch([() => route.name, () => route.query.unread_only], ([name, unreadOnly]) => {
  if (name === 'admin-messages') inbox.setFilters(1, unreadOnly === 'true', !document.hidden)
}, { immediate: true })
onMounted(() => {
  if (route.name === 'messages' && !document.hidden) void inbox.refreshList()
})

function filterUnread(onlyUnread: boolean) {
  if (route.name === 'admin-messages') {
    void router.push({ query: { ...route.query, unread_only: onlyUnread ? 'true' : undefined } })
  } else {
    inbox.setFilters(1, onlyUnread)
  }
}

async function openMessage(message: InboxMessage) {
  if (opening.value) return
  opening.value = message.id
  const sourceRoute = route.name
  actionError.value = ''
  try {
    const read = await inbox.read(message)
    if (read && route.name === sourceRoute) await router.push(notificationDestination(read))
  } catch (error) {
    actionError.value = `打开提醒失败。请重试。 ${adminError(error)}`
  } finally {
    opening.value = ''
  }
}
</script>

<template>
  <section class="resource-page support-page" aria-labelledby="inbox-title">
    <header class="resource-titlebar support-title">
      <h1 id="inbox-title">我的消息</h1>
    </header>
    <div class="resource-panel">
      <div class="resource-actions support-toolbar">
        <el-checkbox :model-value="inbox.unreadOnly" @update:model-value="filterUnread($event === true)">只看未读</el-checkbox>
        <el-button :loading="inbox.loading && !inbox.messages" @click="inbox.refreshList(true)">刷新</el-button>
      </div>
      <el-alert v-if="actionError || inbox.messageError" class="support-error"
        :title="actionError || inbox.messageError" type="error" :closable="false" show-icon />
      <p v-if="inbox.loading && !inbox.messages" role="status">正在加载消息…</p>
      <ul v-if="inbox.messages?.items.length" class="inbox-list">
        <li v-for="message in inbox.messages.items" :key="message.id" :class="['inbox-row', { unread: !message.read_at }]">
          <button type="button" class="inbox-row-button" :disabled="Boolean(opening)" @click="openMessage(message)">
            <span class="inbox-main">
              <span class="inbox-subject">{{ message.title }}</span>
              <el-tag v-if="!message.read_at" size="small" type="danger">未读</el-tag>
            </span>
            <time :datetime="message.sent_at">{{ supportTime(message.sent_at) }}</time>
            <span class="inbox-body">{{ message.body }}</span>
          </button>
        </li>
      </ul>
      <p v-if="inbox.messages && !inbox.messages.items.length" class="support-empty">
        {{ inbox.unreadOnly ? '没有未读消息' : '暂无消息' }}
      </p>
      <div v-if="inbox.messages && (route.name === 'admin-messages' || inbox.messages.total > 20)" class="resource-pagination">
        <el-pagination :current-page="inbox.page" :total="inbox.messages.total" :page-size="20"
          layout="total, prev, pager, next" @current-change="inbox.setFilters($event, inbox.unreadOnly)" />
      </div>
    </div>
  </section>
</template>

<style scoped>
.inbox-list { list-style: none; }
.inbox-row { border-bottom: 1px solid #e3e9f2; }
.inbox-row:last-child { border-bottom: 0; }
.inbox-row.unread { background: #f0f6ff; }
.inbox-row-button {
  width: 100%; background: transparent; border: 0; border-radius: 4px;
  padding: 13px 12px; text-align: left; color: #17243a; font: inherit; cursor: pointer;
  display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 6px 12px;
}
.inbox-row-button:hover { box-shadow: inset 0 0 0 1px #bcd2f1; }
.inbox-row-button:focus-visible { outline: 2px solid #1d5aab; outline-offset: -2px; }
.inbox-main { display: flex; align-items: flex-start; gap: 8px; overflow-wrap: anywhere; }
.unread .inbox-subject { font-weight: 750; }
.inbox-row time, .inbox-body { color: #4d5d71; font-size: .875rem; }
.inbox-body { grid-column: 1 / -1; }
@media (max-width: 600px) {
  .inbox-row-button { grid-template-columns: minmax(0, 1fr); }
}
</style>

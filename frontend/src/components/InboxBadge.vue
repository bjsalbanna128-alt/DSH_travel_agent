<script setup lang="ts">
import { useInboxStore } from '../stores/inbox'

const inbox = useInboxStore()
</script>

<template>
  <span v-if="inbox.unread > 0" class="inbox-count" :aria-label="`${inbox.unread} 条未读消息`">{{ inbox.unread }}</span>
</template>

<style scoped>
.inbox-count {
  display: inline-block; margin-left: 5px; min-width: 21px; padding: 1px 5px;
  border-radius: 12px; background: #b4232c; color: white; font-weight: 700; font-size: 12px; text-align: center;
}
</style>

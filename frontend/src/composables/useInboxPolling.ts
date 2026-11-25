import { computed, onMounted, onScopeDispose, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useInboxStore } from '../stores/inbox'

const POLL_MS = 30_000

export function useInboxPolling() {
  const auth = useAuthStore()
  const inbox = useInboxStore()
  const route = useRoute()
  const active = computed(() => Boolean(auth.user && !route.meta.public &&
    ((auth.role === 'operator' && route.meta.operatorOnly) || (auth.role === 'tourist' && !route.meta.operatorOnly))))
  const isList = computed(() => route.name === 'messages' || route.name === 'admin-messages')
  let timer: number | undefined

  function poll() {
    window.clearTimeout(timer)
    if (!active.value || document.hidden) return
    void inbox.refreshCount()
    if (isList.value) void inbox.refreshList()
    timer = window.setTimeout(poll, POLL_MS)
  }

  watch([active, () => auth.sessionVersion, () => auth.userId, () => auth.role], poll)
  watch(isList, list => {
    if (list) poll()
    else inbox.clearListRequest()
  })
  onMounted(() => {
    document.addEventListener('visibilitychange', poll)
    window.addEventListener('focus', poll)
    poll()
  })
  onScopeDispose(() => {
    document.removeEventListener('visibilitychange', poll)
    window.removeEventListener('focus', poll)
    window.clearTimeout(timer)
  })
}

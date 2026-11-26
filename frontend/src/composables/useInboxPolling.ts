import { computed, onMounted, onScopeDispose, watch } from 'vue'
import { useRoute } from 'vue-router'
import { areaMatches } from '../router'
import { useAuthStore } from '../stores/auth'
import { useInboxStore } from '../stores/inbox'

const POLL_MS = 30_000

export function useInboxPolling() {
  const auth = useAuthStore()
  const inbox = useInboxStore()
  const route = useRoute()
  const active = computed(() => Boolean(auth.user && !route.meta.public &&
    route.name !== 'admin-home' && areaMatches(auth.role, route.meta.area)))
  const isList = computed(() => route.name === 'messages' || route.name === 'admin-messages')
  let timer: number | undefined

  function schedule(includeList: boolean) {
    window.clearTimeout(timer)
    if (!active.value || document.hidden) return
    void inbox.refreshCount()
    if (includeList && isList.value) void inbox.refreshList()
    timer = window.setTimeout(poll, POLL_MS)
  }

  function poll() { schedule(true) }

  watch([active, () => auth.sessionVersion, () => auth.userId, () => auth.role], () => {
    if (!active.value) inbox.cancelCount()
    schedule(false)
  })
  watch(isList, list => {
    if (!list) inbox.clearListRequest()
  })
  onMounted(() => {
    document.addEventListener('visibilitychange', poll)
    window.addEventListener('focus', poll)
    schedule(false)
  })
  onScopeDispose(() => {
    document.removeEventListener('visibilitychange', poll)
    window.removeEventListener('focus', poll)
    window.clearTimeout(timer)
  })
}

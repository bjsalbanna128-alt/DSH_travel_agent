import { defineStore } from 'pinia'
import { ref, shallowRef, watch } from 'vue'
import { adminError } from '../api/adminResources'
import { supportApi } from '../api/support'
import type { PageResult } from '../types/adminResources'
import type { InboxMessage } from '../types/support'
import { useAuthStore } from './auth'

const MERGE_WINDOW_MS = 250

export const useInboxStore = defineStore('inbox', () => {
  const auth = useAuthStore()
  const unread = ref(0)
  const messages = shallowRef<PageResult<InboxMessage>>()
  const messageError = ref('')
  const loading = ref(false)
  const page = ref(1)
  const unreadOnly = ref(false)
  let generation = 0
  let readRevision = 0
  let countRequest: AbortController | undefined
  let listRequest: AbortController | undefined
  let readRequest: AbortController | undefined
  let countStarted = -Infinity
  let listStarted = -Infinity

  function clearListRequest() {
    listRequest?.abort()
    listRequest = undefined
    listStarted = -Infinity
    loading.value = false
  }

  function reset() {
    generation++
    countRequest?.abort()
    countRequest = undefined
    countStarted = -Infinity
    clearListRequest()
    readRequest?.abort()
    readRequest = undefined
    unread.value = 0
    messages.value = undefined
    messageError.value = ''
    page.value = 1
    unreadOnly.value = false
  }
  watch([() => auth.sessionVersion, () => auth.userId, () => auth.role], reset, { flush: 'sync' })

  function cancelCount() {
    countRequest?.abort()
    countRequest = undefined
    countStarted = -Infinity
  }

  function dashboardUnreadReceiver() {
    cancelCount()
    const session = generation
    const appliedReads = readRevision
    return (count: number) => {
      if (session === generation && appliedReads === readRevision) unread.value = count
    }
  }

  async function refreshCount(force = false) {
    if (!auth.user || countRequest || (!force && performance.now() - countStarted < MERGE_WINDOW_MS)) return
    const request = new AbortController()
    const session = generation
    countRequest = request
    countStarted = performance.now()
    try {
      const { unread_count } = await supportApi.unread(auth.role === 'operator', request.signal)
      if (session === generation && !request.signal.aborted) unread.value = unread_count
    } catch {
      // Retain the last successful count through network interruptions.
    } finally {
      if (countRequest === request) countRequest = undefined
    }
  }

  async function refreshList(force = false) {
    if (!auth.user || listRequest || (!force && performance.now() - listStarted < MERGE_WINDOW_MS)) return
    const request = new AbortController()
    const session = generation
    listRequest = request
    listStarted = performance.now()
    loading.value = true
    try {
      const result = await supportApi.inbox(auth.role === 'operator', page.value, unreadOnly.value, request.signal)
      if (session === generation && !request.signal.aborted) {
        if (page.value > 1 && result.items.length === 0 && result.total <= (page.value - 1) * 20) {
          setFilters(Math.max(1, Math.ceil(result.total / 20)), unreadOnly.value)
          return
        }
        messages.value = result
        messageError.value = ''
      }
    } catch (failure) {
      if (session === generation && !request.signal.aborted) messageError.value = adminError(failure)
    } finally {
      if (listRequest === request) {
        listRequest = undefined
        loading.value = false
      }
    }
  }

  function setFilters(nextPage: number, onlyUnread: boolean, fetch = true) {
    clearListRequest()
    if (page.value !== nextPage || unreadOnly.value !== onlyUnread) messages.value = undefined
    page.value = nextPage
    unreadOnly.value = onlyUnread
    messageError.value = ''
    if (fetch) void refreshList(true)
  }

  async function read(message: InboxMessage) {
    if (!auth.user || readRequest) return
    const request = new AbortController()
    const session = generation
    readRequest = request
    try {
      const result = await supportApi.read(auth.role === 'operator', message.id, request.signal)
      if (session !== generation || request.signal.aborted) return
      readRevision++
      cancelCount()
      clearListRequest()
      unread.value = result.unread_count
      if (messages.value) {
        const current = messages.value
        messages.value = unreadOnly.value ? {
          items: current.items.filter(row => row.id !== message.id),
          total: current.total - Number(current.items.some(row => row.id === message.id)),
        } : { ...current, items: current.items.map(row => row.id === message.id ? result.message : row) }
      }
      return result.message
    } catch (error) {
      if (session === generation && !request.signal.aborted) throw error
    } finally {
      if (readRequest === request) readRequest = undefined
    }
  }

  return {
    unread, messages, messageError, loading, page, unreadOnly, refreshCount, refreshList,
    setFilters, clearListRequest, cancelCount, dashboardUnreadReceiver, read,
  }
})

import { onScopeDispose, ref, shallowRef } from 'vue'
import { adminError } from '../api/adminResources'

export function useAdminQuery<T>(query: (signal: AbortSignal) => Promise<T>) {
  const data = shallowRef<T>()
  const loading = ref(false)
  const error = ref('')
  let active: AbortController | undefined

  async function load() {
    active?.abort()
    const request = new AbortController()
    active = request
    loading.value = true
    error.value = ''
    try {
      const result = await query(request.signal)
      if (!request.signal.aborted) data.value = result
    } catch (failure) {
      if (!request.signal.aborted) error.value = adminError(failure)
    } finally {
      if (!request.signal.aborted) loading.value = false
    }
  }

  function clear() {
    active?.abort()
    loading.value = false
    error.value = ''
    data.value = undefined
  }

  onScopeDispose(clear)
  return { data, loading, error, load, clear }
}

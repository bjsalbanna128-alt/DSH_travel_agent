import { ref, watch } from 'vue'
import { fetchRecommendationCover } from '../api/recommendations'
import type { CoverInfo } from '../types/recommendations'

export function useRecommendationCover(source: () => Pick<CoverInfo, 'id' | 'url'> | null | undefined) {
  const url = ref('')
  const failed = ref(false)
  watch(() => source()?.id, async (_, _previous, cleanup) => {
    const cover = source()
    const request = new AbortController()
    let objectUrl = ''
    url.value = ''
    failed.value = false
    cleanup(() => {
      request.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    })
    if (!cover) return
    try {
      const image = await fetchRecommendationCover(cover.url, request.signal)
      if (request.signal.aborted) return
      objectUrl = URL.createObjectURL(image)
      url.value = objectUrl
    } catch {
      if (!request.signal.aborted) failed.value = true
    }
  }, { immediate: true })
  return { url, failed }
}

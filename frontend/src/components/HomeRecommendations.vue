<script setup lang="ts">
import { computed, nextTick, onMounted, onScopeDispose, ref, shallowRef, watch } from 'vue'
import { onBeforeRouteLeave, useRoute } from 'vue-router'
import { fetchRecommendationCover, fetchRecommendations } from '../api/recommendations'
import { useAuthStore } from '../stores/auth'
import type { PublishedRecommendation } from '../types/recommendations'
import { readLoginSession, recommendationWasShown, showRecommendationOnce } from '../utils/recommendationSession'
import RecommendationCard from './RecommendationCard.vue'

interface DisplayableRecommendation {
  content: PublishedRecommendation
  cover: Blob
}

const props = defineProps<{ inputStarted: boolean }>()
const emit = defineEmits<{ closed: [] }>()
const auth = useAuthStore()
const route = useRoute()
const opened = ref(false)
const cards = shallowRef<DisplayableRecommendation[]>([])
const position = ref(0)
const current = computed(() => cards.value[position.value])
const coverUrl = ref('')
const didNavigate = ref(false)
const hovered = ref(false)
const cardFocused = ref(false)
const manuallyPaused = ref(false)
const visible = ref(!document.hidden)
const motion = matchMedia('(prefers-reduced-motion: reduce)')
const reducedMotion = ref(motion.matches)
let restoreFocus = false

function updateMotion() { reducedMotion.value = motion.matches }
function updateVisibility() { visible.value = !document.hidden }
onMounted(() => {
  motion.addEventListener('change', updateMotion)
  document.addEventListener('visibilitychange', updateVisibility)
})
onScopeDispose(() => {
  motion.removeEventListener('change', updateMotion)
  document.removeEventListener('visibilitychange', updateVisibility)
})
onBeforeRouteLeave(() => { didNavigate.value = true })

async function displayableCards(items: PublishedRecommendation[], signal: AbortSignal) {
  const cards: (DisplayableRecommendation | undefined)[] = Array(items.length)
  let next = 0
  async function load() {
    while (!signal.aborted && next < items.length) {
      const index = next++
      const content = items[index]
      let temporaryUrl = ''
      try {
        const cover = await fetchRecommendationCover(content.cover_url, signal)
        if (signal.aborted) return
        temporaryUrl = URL.createObjectURL(cover)
        const image = new Image()
        image.src = temporaryUrl
        await image.decode()
        if (!signal.aborted) cards[index] = { content, cover }
      } catch { /* A failed cover does not prevent other cards from displaying. */ }
      finally { if (temporaryUrl) URL.revokeObjectURL(temporaryUrl) }
    }
  }
  await Promise.all(Array.from({ length: Math.min(4, items.length) }, load))
  return cards.filter(card => card !== undefined)
}

watch(
  [() => auth.userId, () => auth.role, () => auth.sessionVersion, () => auth.loginSession?.id,
    () => props.inputStarted, () => route.name, didNavigate],
  async ([accountId, role, version, loginId, started, routeName, leaving], _prior, cleanup) => {
    const request = new AbortController()
    cleanup(() => {
      request.abort()
      restoreFocus = false
      opened.value = false
      cards.value = []
    })
    if (role !== 'tourist' || !loginId || started || routeName !== 'home' || leaving) return
    const session = { accountId, id: loginId }
    const eligible = () => {
      const saved = readLoginSession()
      return !request.signal.aborted && !props.inputStarted && !didNavigate.value
        && route.name === 'home' && auth.role === 'tourist' && auth.sessionVersion === version
        && auth.userId === accountId && auth.loginSession?.id === loginId
        && saved?.accountId === accountId && saved.id === loginId
    }
    try {
      if (!eligible() || await recommendationWasShown(session) || !eligible()) return
      const items = await fetchRecommendations(request.signal)
      if (!eligible()) return
      const displayable = await displayableCards(items, request.signal)
      if (!displayable.length || !eligible()) return
      await showRecommendationOnce(session, eligible, () => {
        cards.value = displayable
        position.value = 0
        manuallyPaused.value = false
        hovered.value = false
        cardFocused.value = false
        restoreFocus = true
        opened.value = true
      })
    } catch { /* Recommendations load independently of planning. */ }
  },
  { immediate: true, flush: 'sync' },
)

watch([current, opened], ([card, open], _previous, cleanup) => {
  const url = card && open ? URL.createObjectURL(card.cover) : ''
  coverUrl.value = url
  if (url) cleanup(() => URL.revokeObjectURL(url))
}, { flush: 'sync' })

watch([opened, cards, position, manuallyPaused, hovered, cardFocused, visible, reducedMotion], (_, _prior, cleanup) => {
  if (!opened.value || cards.value.length < 2 || manuallyPaused.value || hovered.value
    || cardFocused.value || !visible.value || reducedMotion.value) return
  const timer = window.setTimeout(() => { position.value = (position.value + 1) % cards.value.length }, 5000)
  cleanup(() => window.clearTimeout(timer))
})

function goTo(index: number) {
  manuallyPaused.value = true
  position.value = (index + cards.value.length) % cards.value.length
}

function dropCurrent() {
  cards.value = cards.value.filter((_, index) => index !== position.value)
  if (!cards.value.length) opened.value = false
  else position.value %= cards.value.length
}

function leaveCard(event: FocusEvent) {
  cardFocused.value = (event.currentTarget as HTMLElement).contains(event.relatedTarget as Node | null)
}

async function afterClose() {
  await nextTick()
  if (opened.value) return
  cards.value = []
  if (restoreFocus) emit('closed')
  restoreFocus = false
}
</script>

<template>
  <el-dialog
    v-model="opened" title="旅行推荐" width="min(560px, calc(100% - 24px))"
    class="home-recommendation-dialog" align-center append-to-body destroy-on-close
    :close-on-click-modal="false" @closed="afterClose"
  >
    <div
      v-if="current && coverUrl" class="recommendation-slide"
      @mouseenter="hovered = true" @mouseleave="hovered = false"
      @focusin="cardFocused = true" @focusout="leaveCard"
    >
      <RecommendationCard
        :key="current.content.id" :content="current.content" :cover-url="coverUrl" @image-error="dropCurrent"
      />
    </div>
    <nav
      v-if="cards.length > 1" class="recommendation-controls" aria-label="推荐轮播"
      @mouseenter="hovered = true" @mouseleave="hovered = false"
    >
      <el-button size="small" @click="goTo(position - 1)">上一张</el-button>
      <div class="recommendation-indicators" aria-label="选择推荐卡">
        <button
          v-for="(card, index) in cards" :key="card.content.id" type="button"
          :aria-label="`第 ${index + 1} 张推荐`" :aria-current="position === index ? 'true' : undefined"
          @click="goTo(index)"
        ><span /></button>
      </div>
      <el-button size="small" @click="goTo(position + 1)">下一张</el-button>
    </nav>
  </el-dialog>
</template>

<style scoped>
.recommendation-controls {
  display: flex; align-items: center; justify-content: space-between; gap: 6px; margin-top: 14px;
}
.recommendation-indicators {
  display: flex; flex-wrap: wrap; justify-content: center; max-height: 54px; overflow: auto;
}
.recommendation-indicators button {
  display: grid; place-items: center; height: 26px; width: 24px; border: 0;
  background: transparent; cursor: pointer; border-radius: 3px;
}
.recommendation-indicators span { width: 8px; height: 8px; border-radius: 50%; background: #8291a6; }
.recommendation-indicators [aria-current="true"] span { background: #174e96; width: 11px; height: 11px; }
.recommendation-indicators button:focus-visible { outline: 2px solid #245897; }
@media (max-height: 520px) {
  .recommendation-slide :deep(.recommendation-cover) { max-height: 26dvh; }
  .recommendation-slide :deep(.recommendation-copy) { max-height: 27dvh; }
}
</style>

<script setup lang="ts">
import { useRecommendationCover } from '../composables/useRecommendationCover'
import type { CoverInfo, RecommendationFields } from '../types/recommendations'
import RecommendationCard from './RecommendationCard.vue'

const props = defineProps<{ content: RecommendationFields; cover: CoverInfo | null }>()
const { url, failed } = useRecommendationCover(() => props.cover)
</script>

<template>
  <p v-if="failed" role="status" class="resource-muted">封面预览加载失败。</p>
  <div class="recommendation-previews">
    <section>
      <h3>桌面</h3>
      <RecommendationCard :content="content" :cover-url="failed ? '' : url" @image-error="failed = true" />
    </section>
    <section class="mobile-preview">
      <h3>手机</h3>
      <RecommendationCard :content="content" :cover-url="failed ? '' : url" @image-error="failed = true" />
    </section>
  </div>
</template>

<style scoped>
.recommendation-previews { display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(0, 1fr); gap: 16px; }
.recommendation-previews h3 { font-size: .9rem; margin: 10px 0; color: #3e5168; }
.mobile-preview { width: min(100%, 320px); }
@media (max-width: 760px) {
  .recommendation-previews { grid-template-columns: minmax(0, 1fr); }
}
</style>

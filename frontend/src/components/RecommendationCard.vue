<script setup lang="ts">
import type { RecommendationFields } from '../types/recommendations'

defineProps<{
  content: Pick<RecommendationFields, 'title' | 'place' | 'short_text'>
  coverUrl: string
}>()
defineEmits<{ imageError: [] }>()
</script>

<template>
  <article class="recommendation-card">
    <img
      v-if="coverUrl" :src="coverUrl" :alt="[content.place, content.title].filter(Boolean).join(' · ')"
      class="recommendation-cover" @error="$emit('imageError')"
    >
    <div v-else class="recommendation-cover recommendation-placeholder">暂无封面</div>
    <div class="recommendation-copy" tabindex="0">
      <p v-if="content.place" class="recommendation-place">{{ content.place }}</p>
      <h3>{{ content.title || '未填写标题' }}</h3>
      <p class="recommendation-text">{{ content.short_text }}</p>
    </div>
  </article>
</template>

<style scoped>
.recommendation-card {
  background: #f8fafc; border: 1px solid #e1e7ef; overflow: hidden;
  border-radius: 12px; min-width: 0; color: #17243a;
}
.recommendation-cover {
  display: block; width: 100%; aspect-ratio: 16 / 9; object-fit: cover; object-position: center;
  background: #edf2f8;
}
.recommendation-placeholder { display: grid; place-items: center; color: #546279; }
.recommendation-copy {
  max-height: min(34vh, 12rem); overflow: auto; padding: 14px 18px; overflow-wrap: anywhere;
}
.recommendation-copy:focus-visible { outline: 2px solid #245897; outline-offset: -3px; }
.recommendation-place { margin: 0 0 6px; color: #345477; font-size: .875rem; }
h3 { margin: 0 0 8px; font-size: 1.18rem; }
.recommendation-text { margin: 0; line-height: 1.55; white-space: pre-wrap; }
</style>

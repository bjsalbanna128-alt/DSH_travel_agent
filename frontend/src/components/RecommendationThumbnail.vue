<script setup lang="ts">
import { useRecommendationCover } from '../composables/useRecommendationCover'
import type { CoverInfo } from '../types/recommendations'

const props = defineProps<{ cover: Pick<CoverInfo, 'id' | 'url'> | null; title: string; place: string }>()
const { url, failed } = useRecommendationCover(() => props.cover)
</script>

<template>
  <img
    v-if="url && !failed" class="recommendation-thumbnail" :src="url"
    :alt="[place, title].filter(Boolean).join(' · ')" @error="failed = true"
  >
  <span v-else>{{ failed ? '封面读取失败' : cover ? '加载中…' : '无封面' }}</span>
</template>

<style scoped>
.recommendation-thumbnail { width: 96px; aspect-ratio: 16 / 9; object-fit: cover; border-radius: 5px; }
</style>

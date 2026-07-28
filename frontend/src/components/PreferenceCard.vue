<script setup lang="ts">
import type { UserProfile } from '../types/profile'

defineProps<{
  profile: UserProfile | null
}>()

const paceLabel = (p: string) => {
  const map: Record<string, string> = { relaxed: '轻松', moderate: '适中', intensive: '紧凑' }
  return map[p] || p
}

function avgScore(scores: number[]): string {
  if (!scores.length) return '—'
  return (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(1)
}
</script>

<template>
  <div class="preference-card">
    <div v-if="!profile" class="no-profile">
      <p>暂无旅行画像数据</p>
      <p class="hint">完成一次旅行规划后，系统将自动学习您的偏好</p>
    </div>

    <template v-else>
      <div class="profile-header">
        <h3>旅行偏好画像</h3>
        <el-tag size="small" type="info">已旅行 {{ profile.travel_count }} 次</el-tag>
      </div>

      <div class="profile-section">
        <div class="section-title">兴趣标签</div>
        <div class="tag-row">
          <el-tag
            v-for="tag in profile.interest_tags"
            :key="tag"
            size="small"
            type="primary"
          >
            {{ tag }}
          </el-tag>
          <span v-if="!profile.interest_tags?.length" class="no-data">—</span>
        </div>
      </div>

      <div class="profile-row">
        <span class="profile-label">旅行节奏</span>
        <span>{{ paceLabel(profile.pace_preference) }}</span>
      </div>

      <div class="profile-row">
        <span class="profile-label">日均预算</span>
        <span>{{ profile.avg_budget_per_day_cny > 0 ? `¥${profile.avg_budget_per_day_cny.toLocaleString()}` : '—' }}</span>
      </div>

      <div class="profile-row">
        <span class="profile-label">偏好酒店星级</span>
        <span>{{ '★'.repeat(profile.preferred_hotel_stars) }}</span>
      </div>

      <div v-if="profile.cuisine_preferences?.length" class="profile-section">
        <div class="section-title">饮食偏好</div>
        <div class="tag-row">
          <el-tag
            v-for="c in profile.cuisine_preferences"
            :key="c"
            size="small"
            type="warning"
          >
            {{ c }}
          </el-tag>
        </div>
      </div>

      <div v-if="profile.frequent_destinations?.length" class="profile-section">
        <div class="section-title">常去目的地</div>
        <div class="dest-list">
          <div
            v-for="d in profile.frequent_destinations.slice(0, 5)"
            :key="d.city"
            class="dest-item"
          >
            <span>{{ d.city }}</span>
            <span class="dest-count">{{ d.count }}次</span>
          </div>
        </div>
      </div>

      <div v-if="profile.feedback_scores?.length" class="profile-row">
        <span class="profile-label">平均评分</span>
        <span>{{ avgScore(profile.feedback_scores) }} / 5</span>
      </div>
    </template>
  </div>
</template>

<style scoped>
.preference-card {
  background: #fff; border-radius: 12px; padding: 20px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06);
}
.no-profile { text-align: center; padding: 24px; color: #909399; }
.hint { font-size: 12px; color: #c0c4cc; margin-top: 4px; }

.profile-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.profile-header h3 { font-size: 16px; margin: 0; }

.profile-section { margin-bottom: 12px; }
.section-title { font-size: 13px; color: #909399; margin-bottom: 6px; }
.tag-row { display: flex; gap: 4px; flex-wrap: wrap; }

.profile-row { display: flex; justify-content: space-between; padding: 6px 0; font-size: 14px; color: #606266; }
.profile-label { color: #909399; }

.no-data { font-size: 13px; color: #c0c4cc; }

.dest-list { display: flex; flex-direction: column; gap: 4px; }
.dest-item { display: flex; justify-content: space-between; font-size: 13px; color: #606266; }
.dest-count { color: #909399; }
</style>

<script setup lang="ts">
import { productLabels } from '../types/adminResources'
import { activityLabels, type TemplateContent } from '../types/itineraryTemplates'

defineProps<{ content: TemplateContent }>()
</script>

<template>
  <article class="template-preview">
    <header class="resource-stack">
      <h2>{{ content.title || '未命名模板' }}</h2>
      <div class="resource-actions">
        <span v-if="content.destination">{{ content.destination }}</span>
        <el-tag type="info">{{ content.days.length }} 天</el-tag>
        <el-tag v-for="(tag, index) in content.tags" :key="index">{{ tag }}</el-tag>
      </div>
      <p v-if="content.description" class="template-text">{{ content.description }}</p>
    </header>
    <section v-if="content.tips" class="template-preview-day">
      <h3>行前提示</h3>
      <p class="template-text">{{ content.tips }}</p>
    </section>
    <p v-if="!content.days.length" class="resource-muted">尚未添加日程。</p>
    <section v-for="day in content.days" :key="day.day" class="template-preview-day">
      <h3>第 {{ day.day }} 天<span v-if="day.theme"> · {{ day.theme }}</span></h3>
      <ol v-if="day.activities.length" class="template-activity-preview">
        <li v-for="(activity, index) in day.activities" :key="index">
          <div class="resource-actions">
            <span v-if="activity.time" class="resource-muted">{{ activity.time }}</span>
            <strong>{{ activity.name || '未命名活动' }}</strong>
            <el-tag v-if="activity.category" size="small" type="info">{{ activityLabels[activity.category] }}</el-tag>
          </div>
          <p v-if="activity.description" class="template-text">{{ activity.description }}</p>
          <p v-if="activity.product" class="resource-muted">{{ productLabels[activity.product.type] }} · {{ activity.product.name }}</p>
          <p v-else-if="activity.missingProduct" class="resource-muted">未找到关联商品（{{ activity.missingProduct }}）</p>
        </li>
      </ol>
      <p v-else class="resource-muted">尚未添加活动。</p>
      <p v-if="day.notes" class="template-text resource-muted">{{ day.notes }}</p>
    </section>
  </article>
</template>

<style scoped>
.template-preview { display: grid; gap: 16px; color: #17243a; }
.template-preview h2 { font-size: 24px; }
.template-preview h3 { font-size: 16px; }
.template-preview-day { border: 1px solid #e4e8ef; border-radius: 8px; padding: 14px; display: grid; gap: 10px; }
.template-activity-preview { padding-left: 22px; }
.template-activity-preview li + li { margin-top: 10px; }
.template-text { white-space: pre-wrap; overflow-wrap: anywhere; }
</style>

<script setup lang="ts">
import { ref } from 'vue'
import type { ApprovalRequest } from '../types/travel'

const props = defineProps<{ approval: ApprovalRequest }>()
const emit = defineEmits<{ approve: []; reject: [feedback: string] }>()

const showFeedback = ref(false)
const feedback = ref('')
</script>

<template>
  <el-dialog
    :model-value="true"
    :title="approval.question"
    width="520px"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="false"
  >
    <div class="approval-body">
      <p class="approval-info">
        行程「{{ approval.data?.title }}」({{
          approval.data?.duration_days
        }}天，预估 ¥{{ approval.data?.total_budget_estimate_cny?.toLocaleString() }})
      </p>

      <div v-if="!showFeedback" class="approval-actions">
        <el-button type="primary" size="large" @click="emit('approve')">
          确认行程
        </el-button>
        <el-button size="large" @click="showFeedback = true">
          需要修改
        </el-button>
      </div>

      <div v-else class="feedback-section">
        <el-input
          v-model="feedback"
          type="textarea"
          :rows="3"
          placeholder="请描述你想怎么调整，例如：第三天太满了，删掉杜甫草堂"
        />
        <div class="feedback-actions">
          <el-button @click="showFeedback = false">取消</el-button>
          <el-button
            type="primary"
            :disabled="!feedback.trim()"
            @click="emit('reject', feedback.trim())"
          >
            提交修改
          </el-button>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<style scoped>
.approval-body { text-align: center; }
.approval-info { margin-bottom: 20px; color: #606266; }
.approval-actions { display: flex; gap: 12px; justify-content: center; }
.feedback-section { margin-top: 8px; }
.feedback-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px; }
</style>

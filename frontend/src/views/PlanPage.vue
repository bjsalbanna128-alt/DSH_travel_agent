<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useTravelStore } from '../stores/travel'
import ProgressCard from '../components/ProgressCard.vue'
import MiniMap from '../components/MiniMap.vue'
import DayPlanList from '../components/DayPlanList.vue'

const store = useTravelStore()
const router = useRouter()

const phaseDisplay = computed(() => {
  if (!store.isStreaming) return ''
  return store.progress.current_phase || '规划中...'
})

function goHome() {
  store.cancelPlanning()
  store.reset()
  store.resetClarify()
  router.push('/')
}

function goToDetail() {
  if (store.currentTripId) {
    router.push(`/trip/${store.currentTripId}`)
  }
}

</script>

<template>
  <div class="plan-page">
    <!-- Header -->
    <div class="plan-header">
      <el-button text @click="goHome">← 重新规划</el-button>
      <div class="header-info">
        <span class="query-label">{{ store.userQuery }}</span>
      </div>
      <el-button
        v-if="store.currentTripId && !store.isStreaming"
        type="primary"
        @click="goToDetail"
      >
        {{ store.pendingApproval ? '查看待确认草稿' : '查看行程详情' }} →
      </el-button>
    </div>

    <el-row :gutter="24">
      <!-- Left: progress & messages -->
      <el-col :span="14">
        <!-- Streaming progress -->
        <ProgressCard
          v-if="store.isStreaming || store.progress.agents.length > 0"
          :agents="store.progress.agents"
          :current-phase="phaseDisplay"
          :overall-percent="store.progress.overall_percent"
        />

        <!-- Complete state -->
        <div v-if="!store.isStreaming && store.currentTripId" class="done-card">
          <el-result :icon="store.pendingApproval ? 'info' : 'success'"
            :title="store.pendingApproval ? '草稿已生成，待确认' : '行程已确认'">
            <template #extra>
              <el-button type="primary" @click="goToDetail">查看详情</el-button>
              <el-button @click="goHome">规划新行程</el-button>
            </template>
          </el-result>
        </div>

        <!-- Messages -->
        <div v-if="store.messages.length > 0" class="message-list">
          <div
            v-for="msg in store.messages"
            :key="msg.id"
            :class="['message', `message-${msg.role}`]"
          >
            <div class="message-role">
              {{ msg.role === 'user' ? '你' : msg.role === 'agent' ? 'AI助手' : '系统' }}
            </div>
            <div class="message-content">{{ msg.content }}</div>
          </div>
        </div>

        <!-- Empty prompting state -->
        <div v-if="store.isStreaming && store.dayPlans.length === 0" class="prompting-state">
          <el-icon class="is-loading prompting-icon" :size="36">
            <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="3" stroke-dasharray="31.4 31.4" stroke-linecap="round"/></svg>
          </el-icon>
          <p>AI 正在为你规划行程...</p>
          <p class="prompting-hint">正在调用多个 Agent 协作，请稍候</p>
        </div>
      </el-col>

      <!-- Right: preview -->
      <el-col :span="10">
        <div class="preview-panel">
          <div v-if="store.dayPlans.length === 0 && store.isStreaming" class="preview-empty">
            <p>行程预览将在生成后显示</p>
          </div>

          <!-- Mini map -->
          <MiniMap v-if="store.dayPlans.length > 0" :day-plans="store.dayPlans" />

          <!-- Day plan list -->
          <DayPlanList
            v-if="store.dayPlans.length > 0"
            :day-plans="store.dayPlans"
            :total-budget="store.itinerary?.total_budget_estimate_cny ?? 0"
          />

          <!-- Overall tips -->
          <div v-if="store.itinerary?.overall_tips" class="tips-card">
            <div class="tips-title">旅行建议</div>
            <p>{{ store.itinerary.overall_tips }}</p>
          </div>
        </div>
      </el-col>
    </el-row>


  </div>
</template>

<style scoped>
.plan-page { max-width: 1200px; margin: 0 auto; padding: 20px 16px; }

.plan-header {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;
}
.header-info { flex: 1; text-align: center; }
.query-label {
  font-size: 15px; font-weight: 600; color: #303133;
  background: #f0f2f5; padding: 6px 16px; border-radius: 20px;
}

/* Done card */
.done-card {
  background: #fff; border-radius: 12px; padding: 24px;
  margin-bottom: 16px; text-align: center;
}

/* Messages */
.message-list { margin: 16px 0; max-height: 300px; overflow-y: auto; }
.message { padding: 10px 14px; margin-bottom: 8px; border-radius: 8px; }
.message-user { background: #ecf5ff; }
.message-agent { background: #f0f9eb; }
.message-system { background: #fdf6ec; }
.message-role { font-size: 12px; color: #909399; margin-bottom: 4px; }
.message-content { font-size: 14px; color: #303133; white-space: pre-wrap; }

/* Prompting */
.prompting-state {
  text-align: center; padding: 60px 20px; color: #909399;
}
.prompting-icon { margin-bottom: 16px; color: #409eff; }
.prompting-hint { font-size: 12px; color: #c0c4cc; margin-top: 4px; }

/* Preview */
.preview-panel {
  background: #fff; border-radius: 12px; padding: 16px; min-height: 300px;
  position: sticky; top: 80px;
}
.preview-empty {
  text-align: center; padding: 60px 0; color: #c0c4cc; font-size: 14px;
}
.tips-card {
  margin-top: 16px; padding: 14px; background: #fdf6ec; border-radius: 8px;
}
.tips-title { font-size: 14px; font-weight: 600; color: #e6a23c; margin-bottom: 6px; }
.tips-card p { font-size: 13px; color: #606266; line-height: 1.6; margin: 0; }

/* Approval banner */
</style>

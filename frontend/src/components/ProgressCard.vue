<script setup lang="ts">
import { Check, Loading, Clock } from '@element-plus/icons-vue'
import type { AgentProgress } from '../types/travel'

defineProps<{
  agents: AgentProgress[]
  currentPhase: string
  overallPercent: number
}>()
</script>

<template>
  <div class="progress-card">
    <div class="progress-header">
      <span class="phase-label">{{ currentPhase || '准备中...' }}</span>
    </div>

    <div class="agent-list">
      <div
        v-for="agent in agents"
        :key="agent.agent_name"
        :class="['agent-item', `agent-${agent.status}`]"
      >
        <el-icon :size="16">
          <Check v-if="agent.status === 'done'" style="color: #67c23a" />
          <Loading v-else-if="agent.status === 'running'" style="color: #409eff" class="is-loading" />
          <Clock v-else style="color: #c0c4cc" />
        </el-icon>
        <span class="agent-name">{{ agent.message }}</span>
        <el-tag
          v-if="agent.status === 'running'"
          size="small"
          type="warning"
          :disable-transitions="true"
        >
          进行中
        </el-tag>
        <el-tag
          v-else-if="agent.status === 'done'"
          size="small"
          type="success"
          :disable-transitions="true"
        >
          完成
        </el-tag>
      </div>
    </div>
  </div>
</template>

<style scoped>
.progress-card {
  background: #fff; border-radius: 12px; padding: 20px; margin-bottom: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,.04);
}
.progress-header {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;
}
.phase-label { font-size: 16px; font-weight: 600; color: #303133; }
.percent { font-size: 14px; color: #409eff; font-weight: 600; }

.agent-list { margin-top: 16px; display: flex; flex-direction: column; gap: 6px; }
.agent-item {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px; border-radius: 8px;
  font-size: 13px; color: #606266; background: #fafafa;
}
.agent-running { background: #ecf5ff; }
.agent-done { background: #f0f9eb; }
.agent-name { flex: 1; }
</style>

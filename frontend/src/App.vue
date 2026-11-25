<script setup lang="ts">
import { watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AdminLayout from './components/AdminLayout.vue'
import InboxBadge from './components/InboxBadge.vue'
import { useInboxPolling } from './composables/useInboxPolling'
import { checkOperatorRoute, loginRedirect } from './router'
import { useTravelStore } from './stores/travel'
import { useAuthStore } from './stores/auth'
import './support.css'

const store = useTravelStore()
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
useInboxPolling()

watch(() => auth.sessionVersion, () => {
  store.cancelPlanning()
  store.reset()
  store.resetClarify()
  if (!auth.isLoggedIn && !route.meta.public) {
    void router.replace(loginRedirect(route.fullPath))
  }
})

async function retrySession() {
  await auth.syncSession()
  const destination = checkOperatorRoute(route, auth.role)
  if (destination) await router.replace(destination)
}
</script>

<template>
  <div id="app">
    <main v-if="!route.meta.public && auth.isLoggedIn && !auth.user" class="session-status">
      <template v-if="auth.sessionError">
        <el-alert :title="auth.sessionError" type="error" :closable="false" show-icon />
        <el-button @click="retrySession">重试</el-button>
      </template>
      <p v-else role="status">正在验证登录状态…</p>
    </main>

    <AdminLayout v-else-if="route.meta.operatorOnly && auth.role === 'operator'">
      <router-view :key="auth.sessionVersion + ':' + auth.userId" />
    </AdminLayout>

    <el-container v-else-if="!route.meta.operatorOnly" class="app-container">
      <el-header class="app-header">
        <div class="header-left">
          <router-link to="/" class="logo">AI 旅游规划</router-link>
        </div>
        <div class="header-right">
          <router-link to="/history" class="nav-link">历史行程</router-link>
          <template v-if="auth.role === 'tourist'">
            <router-link :to="{ name: 'messages' }" class="nav-link">我的消息<InboxBadge /></router-link>
            <router-link :to="{ name: 'my-tickets' }" class="nav-link">我的工单</router-link>
          </template>
          <router-link v-if="auth.role === 'operator'" to="/admin" class="nav-link">企业运营后台</router-link>
          <router-link v-if="auth.isLoggedIn" to="/profile" class="nav-link">
            {{ auth.username }}
          </router-link>
          <template v-else>
            <router-link to="/login" class="nav-link">登录</router-link>
            <router-link to="/register" class="nav-link">注册</router-link>
          </template>
        </div>
      </el-header>

      <el-main class="app-main">
        <router-view :key="route.meta.touristOnly ? auth.sessionVersion + ':' + auth.userId : 'travel'" />
      </el-main>
    </el-container>

  </div>
</template>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif; background: #f5f7fa; }
.app-container { min-height: 100vh; }
.app-header {
  display: flex; align-items: center; justify-content: space-between;
  background: #fff; border-bottom: 1px solid #e4e7ed; padding: 0 24px; height: 60px;
}
.header-left .logo { font-size: 20px; font-weight: 700; color: #409eff; text-decoration: none; }
.header-right { display: flex; gap: 16px; align-items: center; }
.nav-link { color: #606266; text-decoration: none; font-size: 14px; }
.nav-link:hover { color: #409eff; }
.app-main { background: #f5f7fa; padding: 24px; }
.session-status { max-width: 480px; margin: 64px auto; padding: 0 16px; }
.session-status .el-button { margin-top: 16px; }
@media (max-width: 620px) {
  .app-header { flex-wrap: wrap; gap: 8px; padding: 10px 14px; min-height: 60px; height: auto; }
  .header-right { flex-wrap: wrap; gap: 9px 12px; }
  .app-main { padding: 16px 12px; }
}
</style>

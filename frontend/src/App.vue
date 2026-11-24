<script setup lang="ts">
import { watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTravelStore } from './stores/travel'
import { useAuthStore } from './stores/auth'

const store = useTravelStore()
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

watch(() => auth.token, () => {
  store.cancelPlanning()
  store.reset()
  store.resetClarify()
  if (!auth.isLoggedIn && !route.meta.public) {
    void router.replace({ name: 'login', query: { redirect: route.fullPath } })
  }
})
</script>

<template>
  <div id="app">
    <el-container class="app-container">
      <el-header class="app-header">
        <div class="header-left">
          <router-link to="/" class="logo">AI 旅游规划</router-link>
        </div>
        <div class="header-right">
          <router-link to="/history" class="nav-link">历史行程</router-link>
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
        <router-view />
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
</style>

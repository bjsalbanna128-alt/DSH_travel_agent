<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { operatorDeniedDestination } from '../router'
import { useAuthStore, type AuthUser } from '../stores/auth'
import InboxBadge from './InboxBadge.vue'
import '../adminResources.css'

const router = useRouter()
const auth = useAuthStore()
const account = ref<AuthUser | null>(null)
const error = ref('')
let request: AbortController | undefined

async function loadSession() {
  request?.abort()
  const controller = new AbortController()
  const version = auth.sessionVersion
  request = controller
  account.value = null
  error.value = ''

  const isCurrent = () => !controller.signal.aborted && version === auth.sessionVersion
  try {
    const response = await fetch('/api/v1/admin/session', {
      headers: auth.getAuthHeader(),
      signal: controller.signal,
      cache: 'no-store',
    })
    if (!isCurrent()) return
    if (response.status === 401) {
      auth.logout()
      return
    }
    if (response.status === 403) {
      void auth.syncSession(true)
      await router.replace(operatorDeniedDestination())
      return
    }
    if (!response.ok) throw new Error('Could not load operator session')
    const session: AuthUser = await response.json()
    if (isCurrent()) account.value = session
  } catch {
    if (isCurrent()) error.value = '后台会话加载失败，请重试。'
  }
}

watch(() => auth.sessionVersion, loadSession, { immediate: true })
onBeforeUnmount(() => request?.abort())
</script>

<template>
  <el-container class="admin-layout">
    <el-header class="admin-header">
      <span class="admin-brand">企业运营后台</span>
      <div class="admin-account">
        <span v-if="account">{{ account.username }}</span>
        <el-button text @click="auth.logout()">退出登录</el-button>
      </div>
    </el-header>

    <el-container v-if="account" class="admin-body">
      <el-aside class="admin-sidebar" width="200px">
        <nav aria-label="运营导航">
          <router-link class="admin-nav-link" to="/admin">首页</router-link>
          <div class="admin-nav-group" aria-label="资源管理">
            <div class="admin-nav-label">资源管理</div>
            <router-link class="admin-nav-link" to="/admin/suppliers">供应商</router-link>
            <router-link class="admin-nav-link" to="/admin/products">商品</router-link>
          </div>
          <div class="admin-nav-group" aria-label="行程与内容">
            <div class="admin-nav-label">行程与内容</div>
            <router-link class="admin-nav-link" to="/admin/itinerary-templates">行程模板</router-link>
            <router-link class="admin-nav-link" to="/admin/recommendations">推荐内容</router-link>
            <router-link class="admin-nav-link" :to="{ name: 'admin-trips' }">行程查询</router-link>
          </div>
          <div class="admin-nav-group" aria-label="消息管理">
            <div class="admin-nav-label">消息管理</div>
            <router-link class="admin-nav-link" :to="{ name: 'admin-messages' }">我的消息<InboxBadge /></router-link>
            <router-link class="admin-nav-link" :to="{ name: 'admin-message-settings' }">消息配置</router-link>
          </div>
          <div class="admin-nav-group" aria-label="客服售后">
            <div class="admin-nav-label">客服售后</div>
            <router-link class="admin-nav-link" :to="{ name: 'admin-tickets' }">工单</router-link>
          </div>
          <router-link class="admin-nav-link" :to="{ name: 'admin-members' }">用户会员</router-link>
        </nav>
      </el-aside>
      <el-main class="admin-main">
        <slot />
      </el-main>
    </el-container>

    <el-main v-else class="admin-status">
      <template v-if="error">
        <el-alert :title="error" type="error" :closable="false" show-icon />
        <el-button @click="loadSession">重试</el-button>
      </template>
      <p v-else role="status">正在验证运营身份…</p>
    </el-main>
  </el-container>
</template>

<style scoped>
.admin-layout { min-height: 100vh; flex-direction: column; color: #17243a; }
.admin-header {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  background: #fff; border-bottom: 1px solid #e4e8ef; padding: 0 28px;
}
.admin-brand { font-size: 19px; font-weight: 700; }
.admin-account { display: flex; align-items: center; gap: 12px; font-size: 14px; }
.admin-sidebar { background: #fff; border-right: 1px solid #e4e8ef; padding: 20px 14px; }
.admin-nav-link {
  display: block; padding: 11px 14px; border-radius: 6px;
  color: #234d91; font-size: 14px; text-decoration: none;
}
.admin-nav-link.router-link-exact-active { background: #edf3ff; font-weight: 600; }
.admin-nav-group { margin-top: 16px; }
.admin-nav-label { color: #5d6878; padding: 0 14px 5px; font-size: 12px; font-weight: 650; }
.admin-main { padding: 32px; }
.admin-status { width: min(100%, 480px); margin: 40px auto; }
.admin-status .el-button { margin-top: 16px; }
@media (max-width: 640px) {
  .admin-header { padding: 0 14px; }
  .admin-body { flex-direction: column; }
  .admin-sidebar { width: 100%; padding: 8px 14px; border-right: 0; border-bottom: 1px solid #e4e8ef; }
  .admin-main { padding: 20px 14px; }
}
</style>

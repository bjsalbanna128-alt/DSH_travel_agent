<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { loginDestination } from '../router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function handleLogin() {
  if (loading.value) return
  if (!username.value || !password.value) {
    error.value = '请填写用户名和密码'
    return
  }
  loading.value = true
  error.value = ''
  try {
    if (await auth.login(username.value, password.value)) {
      await router.replace(loginDestination(route.query.redirect, auth.role))
    }
  } catch (e: any) {
    error.value = e.message || '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <h2>登录</h2>
      <p class="subtitle">使用游客或运营账号登录</p>
      <el-form @submit.prevent="handleLogin" label-position="top">
        <el-form-item label="用户名">
          <el-input v-model="username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="password" type="password" placeholder="请输入密码" show-password />
        </el-form-item>
        <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" style="margin-bottom:12px" />
        <el-button type="primary" :loading="loading" native-type="submit" style="width:100%">
          登录
        </el-button>
      </el-form>
      <p class="switch">
        还没有账号？<router-link to="/register">立即注册</router-link>
      </p>
    </div>
  </div>
</template>

<style scoped>
.auth-page { display: flex; justify-content: center; align-items: center; min-height: 80vh; }
.auth-card { width: 400px; background: #fff; border-radius: 12px; padding: 36px; box-shadow: 0 2px 12px rgba(0,0,0,.08); }
.auth-card h2 { margin: 0 0 4px; font-size: 22px; }
.subtitle { color: #909399; margin: 0 0 24px; font-size: 13px; }
.switch { text-align: center; margin-top: 16px; font-size: 13px; color: #909399; }
.switch a { color: #409eff; }
</style>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()

const username = ref('')
const email = ref('')
const password = ref('')
const password2 = ref('')
const loading = ref(false)
const error = ref('')

async function handleRegister() {
  if (!username.value || !email.value || !password.value) {
    error.value = '请填写所有字段'
    return
  }
  if (password.value !== password2.value) {
    error.value = '两次密码输入不一致'
    return
  }
  if (password.value.length < 6) {
    error.value = '密码长度不能少于 6 位'
    return
  }
  loading.value = true
  error.value = ''
  try {
    await auth.register(username.value, email.value, password.value)
    router.push('/')
  } catch (e: any) {
    error.value = e.message || '注册失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <h2>注册</h2>
      <p class="subtitle">创建账号以使用个性化旅行规划</p>
      <el-form @submit.prevent="handleRegister" label-position="top">
        <el-form-item label="用户名">
          <el-input v-model="username" placeholder="2-50个字符" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="email" placeholder="your@email.com" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="password" type="password" placeholder="至少6位" show-password />
        </el-form-item>
        <el-form-item label="确认密码">
          <el-input v-model="password2" type="password" placeholder="再次输入密码" show-password />
        </el-form-item>
        <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" style="margin-bottom:12px" />
        <el-button type="primary" :loading="loading" native-type="submit" style="width:100%">
          注册
        </el-button>
      </el-form>
      <p class="switch">
        已有账号？<router-link to="/login">立即登录</router-link>
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

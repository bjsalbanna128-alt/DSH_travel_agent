import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

const TOKEN_KEY = 'travel_auth_token'
const USER_KEY = 'travel_auth_user'

interface AuthUser {
  user_id: string
  username: string
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const user = ref<AuthUser | null>(
    JSON.parse(localStorage.getItem(USER_KEY) || 'null')
  )

  const isLoggedIn = computed(() => !!token.value)
  const userId = computed(() => user.value?.user_id || 'anonymous')
  const username = computed(() => user.value?.username || '')

  async function login(username_input: string, password: string) {
    const res = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username_input, password }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '登录失败' }))
      throw new Error(err.detail || '登录失败')
    }
    const data = await res.json()
    _saveAuth(data.access_token, { user_id: data.user_id, username: data.username })
  }

  async function register(username_input: string, email: string, password: string) {
    const res = await fetch('/api/v1/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username_input, email, password }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '注册失败' }))
      throw new Error(err.detail || '注册失败')
    }
    const data = await res.json()
    _saveAuth(data.access_token, { user_id: data.user_id, username: data.username })
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  }

  function getAuthHeader(): Record<string, string> {
    if (token.value) {
      return { Authorization: `Bearer ${token.value}` }
    }
    return {}
  }

  function _saveAuth(tok: string, usr: AuthUser) {
    token.value = tok
    user.value = usr
    localStorage.setItem(TOKEN_KEY, tok)
    localStorage.setItem(USER_KEY, JSON.stringify(usr))
  }

  return { token, user, isLoggedIn, userId, username, login, register, logout, getAuthHeader }
})

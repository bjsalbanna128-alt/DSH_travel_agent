import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

const TOKEN_KEY = 'travel_auth_token'
const USER_KEY = 'travel_auth_user'

export type AuthRole = 'tourist' | 'operator'

export interface AuthUser {
  user_id: string
  username: string
  role: AuthRole
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const user = ref<AuthUser | null>(null)
  const sessionVersion = ref(0)
  const sessionError = ref('')
  let sessionRequest: Promise<void> | null = null
  let credentialAttempt = 0

  const isLoggedIn = computed(() => !!token.value)
  const userId = computed(() => user.value?.user_id || 'anonymous')
  const username = computed(() => user.value?.username || '')
  const role = computed(() => user.value?.role)

  function login(username: string, password: string) {
    return authenticate('login', { username, password }, '登录失败')
  }

  function register(username: string, email: string, password: string) {
    return authenticate('register', { username, email, password }, '注册失败')
  }

  async function authenticate(
    action: 'login' | 'register',
    fields: Record<string, string>,
    fallback: string,
  ) {
    const attempt = ++credentialAttempt
    try {
      const res = await fetch(`/api/v1/auth/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(fields),
      })
      const data = await res.json().catch(() => null)
      if (attempt !== credentialAttempt) return false
      if (!res.ok || !data) {
        throw new Error(typeof data?.detail === 'string' ? data.detail : fallback)
      }
      beginSession()
      token.value = data.access_token
      localStorage.setItem(TOKEN_KEY, data.access_token)
      saveUser({ user_id: data.user_id, username: data.username, role: data.role })
      return true
    } catch (error) {
      if (attempt !== credentialAttempt) return false
      throw error
    }
  }

  function syncSession(refresh = false): Promise<void> {
    if (sessionRequest) return sessionRequest
    if (!token.value || (!refresh && user.value)) return Promise.resolve()

    const version = sessionVersion.value
    const headers = getAuthHeader()
    sessionError.value = ''
    if (refresh) user.value = null

    sessionRequest = (async () => {
      try {
        const res = await fetch('/api/v1/auth/me', { headers, cache: 'no-store' })
        if (version !== sessionVersion.value) return
        if (res.status === 401) {
          logout()
          return
        }
        if (!res.ok) throw new Error('Could not restore session')
        const account: AuthUser = await res.json()
        if (version === sessionVersion.value) saveUser(account)
      } catch {
        if (version === sessionVersion.value) {
          sessionError.value = '登录状态加载失败，请重试。'
        }
      } finally {
        if (version === sessionVersion.value) sessionRequest = null
      }
    })()
    return sessionRequest
  }

  function logout() {
    credentialAttempt++
    beginSession()
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

  function beginSession() {
    sessionVersion.value++
    sessionRequest = null
    sessionError.value = ''
  }

  function saveUser(account: AuthUser) {
    user.value = account
    localStorage.setItem(USER_KEY, JSON.stringify(account))
  }

  return {
    token, user, isLoggedIn, userId, username, role, sessionVersion, sessionError,
    login, register, logout, getAuthHeader, syncSession,
  }
})

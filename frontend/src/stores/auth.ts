import { defineStore } from 'pinia'
import { ref, computed, onScopeDispose } from 'vue'
import {
  LOGIN_SESSION_KEY, randomSessionId, readLoginSession, recoverLegacySession,
  saveLoginSession, type LoginSession,
} from '../utils/recommendationSession'

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
  const loginSession = ref<LoginSession>()
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
      saveLoginSession()
      try {
        const session = { accountId: data.user_id, id: randomSessionId() }
        if (saveLoginSession(session)) loginSession.value = session
      } catch { /* Login remains available without display tracking. */ }
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
        if (version === sessionVersion.value) {
          saveUser(account)
          if (account.role === 'tourist') void restoreLoginSession(account.user_id, version)
        }
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
    saveLoginSession()
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
    loginSession.value = undefined
  }

  function saveUser(account: AuthUser) {
    user.value = account
    localStorage.setItem(USER_KEY, JSON.stringify(account))
  }

  async function restoreLoginSession(accountId: string, version: number) {
    const stored = readLoginSession()
    if (stored) {
      loginSession.value = stored.accountId === accountId ? stored : undefined
      return
    }
    const activeToken = token.value
    try {
      const id = await recoverLegacySession(accountId)
      if (sessionVersion.value !== version || activeToken !== localStorage.getItem(TOKEN_KEY)) return
      const current = readLoginSession()
      if (current && current.accountId !== accountId) return
      const session = current ?? { accountId, id }
      if (saveLoginSession(session)) loginSession.value = session
    } catch { /* The home page can still be used when storage is unavailable. */ }
  }

  function syncOtherTab(event: StorageEvent) {
    if (event.key !== TOKEN_KEY && event.key !== LOGIN_SESSION_KEY && event.key !== null) return
    const currentToken = localStorage.getItem(TOKEN_KEY)
    const current = readLoginSession()
    if (currentToken === token.value) {
      if (!user.value || current?.accountId === user.value.user_id || !current) {
        loginSession.value = user.value && current?.accountId === user.value.user_id ? current : undefined
        return
      }
    }
    credentialAttempt++
    beginSession()
    user.value = null
    token.value = currentToken
    if (currentToken) void syncSession()
  }

  window.addEventListener('storage', syncOtherTab)
  onScopeDispose(() => window.removeEventListener('storage', syncOtherTab))

  return {
    token, user, isLoggedIn, userId, username, role, sessionVersion, sessionError, loginSession,
    login, register, logout, getAuthHeader, syncSession,
  }
})

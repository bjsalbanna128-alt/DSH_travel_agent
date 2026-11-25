import { ElMessage } from 'element-plus'
import { createRouter, createWebHistory, type RouteLocationNormalized } from 'vue-router'
import { useAuthStore, type AuthRole } from '../stores/auth'

declare module 'vue-router' {
  interface RouteMeta {
    public?: boolean
    operatorOnly?: boolean
  }
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('../views/HomePage.vue'),
    },
    {
      path: '/plan',
      name: 'plan',
      component: () => import('../views/PlanPage.vue'),
    },
    {
      path: '/chat',
      name: 'chat',
      component: () => import('../views/ChatPage.vue'),
    },
    {
      path: '/trip/:tripId',
      name: 'trip-detail',
      component: () => import('../views/TripDetailPage.vue'),
    },
    {
      path: '/history',
      name: 'history',
      component: () => import('../views/HistoryPage.vue'),
    },
    {
      path: '/trip/:tripId/edit',
      name: 'trip-edit',
      component: () => import('../views/TripEditPage.vue'),
    },
    {
      path: '/profile',
      name: 'profile',
      component: () => import('../views/ProfilePage.vue'),
    },
    {
      path: '/admin',
      meta: { operatorOnly: true },
      children: [
        {
          path: '',
          name: 'admin-home',
          component: () => import('../views/AdminHomePage.vue'),
        },
        {
          path: 'suppliers',
          name: 'admin-suppliers',
          component: () => import('../views/AdminSuppliersPage.vue'),
        },
        {
          path: 'products',
          name: 'admin-products',
          component: () => import('../views/AdminProductsPage.vue'),
        },
        {
          path: 'products/:id',
          name: 'admin-product-details',
          component: () => import('../views/AdminProductDetailPage.vue'),
        },
      ],
    },
    {
      path: '/login',
      name: 'login',
      meta: { public: true },
      component: () => import('../views/LoginPage.vue'),
    },
    {
      path: '/register',
      name: 'register',
      meta: { public: true },
      component: () => import('../views/RegisterPage.vue'),
    },
  ],
})

export function loginRedirect(path: string) {
  return { name: 'login', query: { redirect: path } }
}

export function loginDestination(redirect: unknown, role: AuthRole | undefined) {
  if (typeof redirect === 'string' && redirect.startsWith('/') && !/^\/[\/\\]/.test(redirect)) {
    const target = router.resolve(redirect)
    if (target.matched.length && !target.meta.public) return target.fullPath
  }
  return { name: role === 'operator' ? 'admin-home' : 'home' }
}

export function operatorDeniedDestination() {
  ElMessage.warning('需要运营身份才能访问企业运营后台')
  return { name: 'home' }
}

export function checkOperatorRoute(to: RouteLocationNormalized, role: AuthRole | undefined) {
  if (to.meta.operatorOnly && role === 'tourist') return operatorDeniedDestination()
}

router.beforeEach(async (to) => {
  if (to.meta.public) return
  const auth = useAuthStore()
  if (!auth.isLoggedIn) return loginRedirect(to.fullPath)

  await auth.syncSession()
  if (!auth.isLoggedIn) return loginRedirect(to.fullPath)
  return checkOperatorRoute(to, auth.role)
})

export default router

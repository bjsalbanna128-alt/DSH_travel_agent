import { ElMessage } from 'element-plus'
import { createRouter, createWebHistory, type RouteLocationNormalized } from 'vue-router'
import { useAuthStore, type AuthRole } from '../stores/auth'

declare module 'vue-router' {
  interface RouteMeta {
    public?: boolean
    operatorOnly?: boolean
    touristOnly?: boolean
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
      path: '/messages',
      name: 'messages',
      meta: { touristOnly: true },
      component: () => import('../views/InboxPage.vue'),
    },
    {
      path: '/messages/:id',
      name: 'message-detail',
      meta: { touristOnly: true },
      component: () => import('../views/InboxDetailPage.vue'),
    },
    {
      path: '/tickets',
      name: 'my-tickets',
      meta: { touristOnly: true },
      component: () => import('../views/TicketListPage.vue'),
    },
    {
      path: '/tickets/:id',
      name: 'my-ticket-detail',
      meta: { touristOnly: true },
      component: () => import('../views/TicketDetailPage.vue'),
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
        {
          path: 'itinerary-templates',
          name: 'admin-itinerary-templates',
          component: () => import('../views/AdminItineraryTemplatesPage.vue'),
        },
        {
          path: 'itinerary-templates/new',
          name: 'admin-itinerary-template-new',
          component: () => import('../views/AdminItineraryTemplateEditor.vue'),
        },
        {
          path: 'itinerary-templates/:id/edit',
          name: 'admin-itinerary-template-edit',
          component: () => import('../views/AdminItineraryTemplateEditor.vue'),
        },
        {
          path: 'recommendations',
          name: 'admin-recommendations',
          component: () => import('../views/AdminRecommendationsPage.vue'),
        },
        {
          path: 'recommendations/new',
          name: 'admin-recommendation-new',
          component: () => import('../views/AdminRecommendationEditor.vue'),
        },
        {
          path: 'recommendations/:id/edit',
          name: 'admin-recommendation-edit',
          component: () => import('../views/AdminRecommendationEditor.vue'),
        },
        {
          path: 'messages',
          name: 'admin-messages',
          component: () => import('../views/InboxPage.vue'),
        },
        {
          path: 'messages/:id',
          name: 'admin-message-detail',
          component: () => import('../views/InboxDetailPage.vue'),
        },
        {
          path: 'message-settings',
          name: 'admin-message-settings',
          component: () => import('../views/MessageSettingsPage.vue'),
        },
        {
          path: 'tickets',
          name: 'admin-tickets',
          component: () => import('../views/TicketListPage.vue'),
          props: { operator: true },
        },
        {
          path: 'tickets/:id',
          name: 'admin-ticket-detail',
          component: () => import('../views/TicketDetailPage.vue'),
          props: { operator: true },
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
  if (to.meta.touristOnly && role === 'operator') return { name: 'admin-home' }
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

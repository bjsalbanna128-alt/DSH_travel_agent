import { ElMessage } from 'element-plus'
import { createRouter, createWebHistory, type RouteMeta } from 'vue-router'
import { useAuthStore, type AuthRole } from '../stores/auth'

declare module 'vue-router' {
  interface RouteMeta {
    public?: boolean
    /** Area a route belongs to: 'c' for the tourist app, 'b' for the operator console. */
    area?: 'c' | 'b'
    /** Remount the view when the signed-in account changes. */
    sessionScoped?: boolean
  }
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      meta: { area: 'c' },
      component: () => import('../views/HomePage.vue'),
    },
    {
      path: '/plan',
      name: 'plan',
      meta: { area: 'c' },
      component: () => import('../views/PlanPage.vue'),
    },
    {
      path: '/chat',
      name: 'chat',
      meta: { area: 'c' },
      component: () => import('../views/ChatPage.vue'),
    },
    {
      path: '/inspiration',
      name: 'inspiration',
      meta: { area: 'c' },
      component: () => import('../views/InspirationPage.vue'),
    },
    {
      path: '/trip/:tripId',
      name: 'trip-detail',
      meta: { area: 'c' },
      component: () => import('../views/TripDetailPage.vue'),
    },
    {
      path: '/history',
      name: 'history',
      meta: { area: 'c' },
      component: () => import('../views/HistoryPage.vue'),
    },
    {
      path: '/trip/:tripId/edit',
      name: 'trip-edit',
      meta: { area: 'c' },
      component: () => import('../views/TripEditPage.vue'),
    },
    {
      path: '/profile',
      name: 'profile',
      meta: { area: 'c' },
      component: () => import('../views/ProfilePage.vue'),
    },
    {
      path: '/messages',
      name: 'messages',
      meta: { area: 'c', sessionScoped: true },
      component: () => import('../views/InboxPage.vue'),
    },
    {
      path: '/membership',
      name: 'membership',
      meta: { area: 'c' },
      component: () => import('../views/MemberCenterPage.vue'),
    },
    {
      path: '/messages/:id',
      name: 'message-detail',
      meta: { area: 'c', sessionScoped: true },
      component: () => import('../views/InboxDetailPage.vue'),
    },
    {
      path: '/tickets',
      name: 'my-tickets',
      meta: { area: 'c', sessionScoped: true },
      component: () => import('../views/TicketListPage.vue'),
    },
    {
      path: '/tickets/:id',
      name: 'my-ticket-detail',
      meta: { area: 'c', sessionScoped: true },
      component: () => import('../views/TicketDetailPage.vue'),
    },
    {
      path: '/admin',
      meta: { area: 'b' },
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
        {
          path: 'members',
          name: 'admin-members',
          component: () => import('../views/AdminMembersPage.vue'),
        },
        {
          path: 'members/:id',
          name: 'admin-member-detail',
          component: () => import('../views/AdminMemberDetailPage.vue'),
        },
        {
          path: 'trips',
          name: 'admin-trips',
          component: () => import('../views/AdminTripsPage.vue'),
        },
        {
          path: 'trips/:id',
          name: 'admin-trip-detail',
          component: () => import('../views/AdminTripDetailPage.vue'),
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

/** Landing route for a signed-in role. */
export function roleHome(role: AuthRole) {
  return { name: role === 'operator' ? 'admin-home' : 'home' }
}

/** Whether a route area belongs to the given role. Routes without an area stay reachable. */
export function areaMatches(role: AuthRole | undefined, area: RouteMeta['area']) {
  if (!area) return true
  return area === (role === 'operator' ? 'b' : 'c')
}

/**
 * Post-login destination. The redirect is honoured only when it points inside the
 * signed-in role's own area, so a tourist never lands on an operator URL.
 */
export function loginDestination(redirect: unknown, role: AuthRole | undefined) {
  if (typeof redirect === 'string' && redirect.startsWith('/') && !/^\/[\/\\]/.test(redirect)) {
    const target = router.resolve(redirect)
    if (target.matched.length && !target.meta.public && areaMatches(role, target.meta.area)) {
      return target.fullPath
    }
  }
  return role ? roleHome(role) : { name: 'home' }
}

/**
 * Feedback for an explicit operator-only rejection (HTTP 403).
 * Walking into the wrong area is a silent redirect instead, never a warning.
 */
export function operatorDeniedDestination() {
  ElMessage.warning('需要运营身份才能访问企业运营后台')
  const auth = useAuthStore()
  return auth.role ? roleHome(auth.role) : { name: 'login' }
}

router.beforeEach(async (to) => {
  const auth = useAuthStore()

  if (to.meta.public) {
    if (!auth.isLoggedIn) return
    await auth.syncSession()
    return auth.role ? roleHome(auth.role) : undefined
  }

  if (!auth.isLoggedIn) return loginRedirect(to.fullPath)
  await auth.syncSession()
  if (!auth.isLoggedIn) return loginRedirect(to.fullPath)

  // Role is still unknown because the session request failed: let the app render its
  // status screen instead of bouncing the user, so no area is shown in the meantime.
  if (!auth.role) return
  if (!areaMatches(auth.role, to.meta.area)) return roleHome(auth.role)
})

export default router

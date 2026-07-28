import { createRouter, createWebHistory } from 'vue-router'

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
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginPage.vue'),
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('../views/RegisterPage.vue'),
    },
  ],
})

export default router

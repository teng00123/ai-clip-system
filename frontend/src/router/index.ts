import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    // ── Public (no auth, no navbar) ──────────────────────────────────────────
    { path: '/login',    component: () => import('@/views/LoginView.vue') },
    { path: '/register', component: () => import('@/views/RegisterView.vue') },

    // ── Authenticated (with navbar via AppLayout) ────────────────────────────
    {
      path: '/',
      component: () => import('@/components/common/AppLayout.vue'),
      meta: { requiresAuth: true },
      children: [
        { path: '', redirect: '/dashboard' },
        {
          path: '/dashboard',
          component: () => import('@/views/DashboardView.vue'),
        },
        {
          path: '/project/:projectId/guide',
          component: () => import('@/views/GuideView.vue'),
        },
        {
          path: '/project/:projectId/script',
          component: () => import('@/views/ScriptView.vue'),
        },
        {
          path: '/project/:projectId/upload',
          component: () => import('@/views/VideoUploadView.vue'),
        },
        {
          path: '/project/:projectId/clip/:jobId?',
          component: () => import('@/views/ClipView.vue'),
        },
        {
          path: '/project/:projectId/export/:jobId',
          component: () => import('@/views/ExportView.vue'),
        },
      ],
    },

    // ── Catch-all ────────────────────────────────────────────────────────────
    { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
  ],
})

router.beforeEach((to, _from, next) => {
  const authStore = useAuthStore()
  if (to.meta.requiresAuth && !authStore.isLoggedIn) {
    next('/login')
  } else if ((to.path === '/login' || to.path === '/register') && authStore.isLoggedIn) {
    next('/dashboard')
  } else {
    next()
  }
})

export default router

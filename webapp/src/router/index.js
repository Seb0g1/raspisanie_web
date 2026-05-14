import { createRouter, createWebHistory } from 'vue-router'
import { api } from '../api'

const routes = [
  { path: '/login', name: 'Login', component: () => import('../views/Login.vue'), meta: { public: true } },
  { path: '/', name: 'Dashboard', component: () => import('../views/Dashboard.vue') },
  { path: '/users', name: 'Users', component: () => import('../views/Users.vue') },
  { path: '/broadcast', name: 'Broadcast', component: () => import('../views/Broadcast.vue') },
  { path: '/feedback', name: 'Feedback', component: () => import('../views/Feedback.vue') },
  { path: '/upload', name: 'Upload', component: () => import('../views/Upload.vue') },
  { path: '/ads', name: 'Ads', component: () => import('../views/Ads.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  if (to.meta.public) {
    try {
      const res = await fetch('/api/me', { credentials: 'include' })
      const data = await res.json()
      if (data.logged_in) return { name: 'Dashboard' }
    } catch (_) {}
    return true
  }
  try {
    const res = await fetch('/api/me', { credentials: 'include' })
    const data = await res.json()
    if (!data.logged_in) return { name: 'Login', query: { redirect: to.fullPath } }
  } catch (_) {
    return { name: 'Login', query: { redirect: to.fullPath } }
  }
  return true
})

export default router

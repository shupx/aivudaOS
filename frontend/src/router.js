import { createRouter, createWebHistory } from 'vue-router'
import LoginView from './views/LoginView.vue'
import StatusView from './views/StatusView.vue'
import ConfigView from './views/ConfigView.vue'
import { isAuthed } from './services/droneClient'

const routes = [
  { path: '/', redirect: '/status' },
  { path: '/login', component: LoginView },
  { path: '/status', component: StatusView },
  { path: '/config', component: ConfigView },
  { path: '/:pathMatch(.*)*', redirect: '/status' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  if (to.path === '/login' && isAuthed()) {
    return '/status'
  }
  if (to.path !== '/login' && !isAuthed()) {
    return '/login'
  }
  return true
})

export default router

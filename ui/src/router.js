import { createRouter, createWebHistory } from 'vue-router'
import LoginView from './views/LoginView.vue'
import DashboardView from './views/DashboardView.vue'
import StatusView from './views/StatusView.vue'
import AppsView from './views/AppsView.vue'
import AppDetailView from './views/AppDetailView.vue'
import OnlineStoreView from './views/OnlineStoreView.vue'
import OnlineStoreDetailView from './views/OnlineStoreDetailView.vue'
import { appState } from './state/appState'

const routes = [
  { path: '/', redirect: '/dashboard/apps' },
  { path: '/login', component: LoginView },
  {
    path: '/dashboard',
    component: DashboardView,
    children: [
      { path: '', redirect: '/dashboard/apps' },
      { path: 'status', component: StatusView },
      { path: 'apps', component: AppsView },
      { path: 'apps/:appId', component: AppDetailView },
      { path: 'store', component: OnlineStoreView },
      { path: 'store/:appId', component: OnlineStoreDetailView },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard/apps' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const isAuthed = Boolean(appState.token)
  if (to.path === '/login' && isAuthed) {
    return '/dashboard/apps'
  }
  if (to.path !== '/login' && !isAuthed) {
    return '/login'
  }
  return true
})

export default router

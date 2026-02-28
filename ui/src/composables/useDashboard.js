import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { appState } from '../state/appState'
import { fetchMe, logout } from '../services/core/auth'
import { useAppsPanel } from './useAppsPanel'

export function useDashboard() {
  const route = useRoute()
  const router = useRouter()
  const { refresh } = useAppsPanel()

  const sidebarCollapsed = computed(() => appState.sidebarCollapsed)
  const isStatusRoute = computed(() => route.path === '/dashboard/status')
  const isAppsRoute = computed(() => route.path.startsWith('/dashboard/apps'))
  const user = computed(() => appState.user)
  const role = computed(() => appState.role)

  onMounted(async () => {
    try {
      if (!appState.user) {
        await fetchMe()
      }
      await refresh()
    } catch {
      logout()
      router.replace('/login')
    }
  })

  function toggleSidebar() {
    appState.sidebarCollapsed = !appState.sidebarCollapsed
  }

  function goStatus() {
    router.push('/dashboard/status')
  }

  function goApps() {
    router.push('/dashboard/apps')
  }

  function doLogout() {
    logout()
    router.replace('/login')
  }

  return {
    sidebarCollapsed,
    isStatusRoute,
    isAppsRoute,
    user,
    role,
    goStatus,
    goApps,
    toggleSidebar,
    doLogout,
  }
}

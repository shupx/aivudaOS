import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { appState, setLocale } from '../state/appState'
import { fetchMe, logout } from '../services/core/auth'
import { useAppsPanel } from './useAppsPanel'

export function useDashboard() {
  const route = useRoute()
  const router = useRouter()
  const { refresh } = useAppsPanel()

  const sidebarCollapsed = computed(() => appState.sidebarMode !== 'expanded')
  const sidebarMode = computed(() => appState.sidebarMode || 'icon')
  const isStatusRoute = computed(() => route.path === '/dashboard/status')
  const isAppsRoute = computed(() => {
    return route.path.startsWith('/dashboard/apps') && !route.path.startsWith('/dashboard/apps/configs')
  })
  const isConfigRoute = computed(() => route.path.startsWith('/dashboard/apps/configs'))
  const isStoreRoute = computed(() => route.path.startsWith('/dashboard/store'))
  const isSystemSettingsRoute = computed(() => route.path.startsWith('/dashboard/settings'))
  const locale = computed(() => appState.locale)
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

  function collapseSidebar() {
    if (appState.sidebarMode === 'expanded') {
      appState.sidebarMode = 'icon'
    } else if (appState.sidebarMode === 'icon') {
      appState.sidebarMode = 'hidden'
    }
    appState.sidebarCollapsed = appState.sidebarMode !== 'expanded'
  }

  function expandSidebar() {
    if (appState.sidebarMode === 'hidden') {
      appState.sidebarMode = 'icon'
    } else if (appState.sidebarMode === 'icon') {
      appState.sidebarMode = 'expanded'
    }
    appState.sidebarCollapsed = appState.sidebarMode !== 'expanded'
  }

  function goStatus() {
    router.push('/dashboard/status')
  }

  function goApps() {
    router.push('/dashboard/apps')
  }

  function goConfigs() {
    router.push('/dashboard/apps/configs')
  }

  function goStore() {
    router.push('/dashboard/store')
  }

  function goSystemSettings() {
    router.push('/dashboard/settings')
  }

  function doLogout() {
    logout()
    router.replace('/login')
  }

  function changeLocale(nextLocale) {
    setLocale(nextLocale)
  }

  return {
    sidebarCollapsed,
    sidebarMode,
    isStatusRoute,
    isAppsRoute,
    isConfigRoute,
    isStoreRoute,
    isSystemSettingsRoute,
    locale,
    user,
    role,
    goStatus,
    goApps,
    goConfigs,
    goStore,
    goSystemSettings,
    collapseSidebar,
    expandSidebar,
    doLogout,
    changeLocale,
  }
}

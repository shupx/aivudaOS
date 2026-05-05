import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import i18n from '../i18n'
import { appState, markGatewayOnline, patchApp, setAppDetail, setApps, setBusy, setRestartBusy } from '../state/appState'
import {
  fetchAppStatus,
  fetchInstalledApps,
  restartApp,
  restartAutostartApps,
  setAutostart,
  startAutostartApps,
  startApp,
  stopAllApps,
  stopApp,
} from '../services/core/apps'
import { useAppUploadInstallModal } from './useAppUploadInstallModal'

let pollTimer = null
const APPS_COMPACT_MODE_STORAGE_KEY = 'aivuda_ui_apps_compact_mode'
const FAVORITE_APP_IDS_STORAGE_KEY = 'aivuda_ui_favorite_app_ids'

function readFavoriteAppIds() {
  try {
    const parsed = JSON.parse(localStorage.getItem(FAVORITE_APP_IDS_STORAGE_KEY) || '[]')
    if (!Array.isArray(parsed)) return []
    return [...new Set(parsed.map((item) => String(item || '').trim()).filter(Boolean))]
  } catch {
    return []
  }
}

function writeFavoriteAppIds(appIds) {
  localStorage.setItem(FAVORITE_APP_IDS_STORAGE_KEY, JSON.stringify(appIds))
}

function mergeAppsWithDetail(items) {
  return items.map((item) => {
    const detail = appState.appDetailsById[item.app_id]
    const description = detail?.manifest?.description || ''
    return {
      ...item,
      description,
    }
  })
}

async function hydrateDescriptions(apps) {
  const missingIds = apps
    .filter((item) => !appState.appDetailsById[item.app_id])
    .map((item) => item.app_id)

  await Promise.all(
    missingIds.map(async (appId) => {
      try {
        const detail = await fetchAppStatus(appId)
        setAppDetail(appId, detail)
      } catch {
      }
    }),
  )
}

async function refresh() {
  appState.appsLoading = true
  appState.appsError = ''
  try {
    const items = await fetchInstalledApps()
    await hydrateDescriptions(items)
    setApps(mergeAppsWithDetail(items))
    markGatewayOnline(true)
  } catch (err) {
    appState.appsError = String(err?.message || err || i18n.global.t('errors.loadFailed'))
    markGatewayOnline(false)
  } finally {
    appState.appsLoading = false
  }
}

async function toggleRunning(app, nextValue) {
  const appId = app.app_id
  const previousValue = Boolean(app.running)
  patchApp(appId, { running: Boolean(nextValue) })
  setBusy(appId, true)

  try {
    if (nextValue) {
      await startApp(appId)
    } else {
      await stopApp(appId)
    }
    await refresh()
  } catch (err) {
    patchApp(appId, { running: previousValue })
    appState.appsError = String(err?.message || err || i18n.global.t('errors.operationFailed'))
  } finally {
    setBusy(appId, false)
  }
}

async function toggleAutostart(app, nextValue) {
  const appId = app.app_id
  const previousValue = Boolean(app.autostart)
  patchApp(appId, { autostart: Boolean(nextValue) })
  setBusy(appId, true)

  try {
    await setAutostart(appId, nextValue)
    await refresh()
  } catch (err) {
    patchApp(appId, { autostart: previousValue })
    appState.appsError = String(err?.message || err || i18n.global.t('errors.operationFailed'))
  } finally {
    setBusy(appId, false)
  }
}

async function restartSingleApp(app) {
  const appId = app?.app_id
  if (!appId) return

  setBusy(appId, true)
  setRestartBusy(appId, true)
  try {
    await restartApp(appId)
    await refresh()
  } catch (err) {
    appState.appsError = String(err?.message || err || i18n.global.t('errors.operationFailed'))
  } finally {
    setRestartBusy(appId, false)
    setBusy(appId, false)
  }
}

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(() => {
    refresh()
  }, 3000)
}

function stopPolling() {
  if (!pollTimer) return
  clearInterval(pollTimer)
  pollTimer = null
}

function isAppsPollingRoute(path) {
  const value = String(path || '')
  if (!value.startsWith('/dashboard/apps')) {
    return false
  }
  if (value.startsWith('/dashboard/apps/configs')) {
    return false
  }
  return true
}

export function useAppsPanel() {
  const route = useRoute()
  const router = useRouter()

  const storedSortOption = localStorage.getItem('APPS_SORT_OPTION') || 'name'
  const storedSortDesc = localStorage.getItem('APPS_SORT_DESC')
  const sortOption = ref(storedSortOption) // name | autostart | installed_at
  const sortDesc = ref(storedSortDesc === null ? storedSortOption === 'installed_at' : storedSortDesc === '1')
  const appsSortDropdownVisible = ref(false)
  const favoriteAppIds = ref(readFavoriteAppIds())
  const favoriteAppIdSet = computed(() => new Set(favoriteAppIds.value))

  const apps = computed(() => {
    const list = [...appState.apps]
    const desc = sortDesc.value ? -1 : 1
    return list.sort((a, b) => {
      const aFavorite = favoriteAppIdSet.value.has(String(a?.app_id || '')) ? 1 : 0
      const bFavorite = favoriteAppIdSet.value.has(String(b?.app_id || '')) ? 1 : 0
      if (aFavorite !== bFavorite) return bFavorite - aFavorite

      if (sortOption.value === 'autostart') {
        const aVal = a.autostart ? 1 : 0
        const bVal = b.autostart ? 1 : 0
        if (aVal !== bVal) return (bVal - aVal) * desc
      } else if (sortOption.value === 'installed_at') {
        const aVal = a.installed_at || 0
        const bVal = b.installed_at || 0
        if (aVal !== bVal) return (aVal - bVal) * desc
      }
      // fallback to name sort
      const aName = a.name || a.app_id || ''
      const bName = b.name || b.app_id || ''
      return aName.localeCompare(bName) * desc
    })
  })
  const loading = computed(() => appState.appsLoading)
  const error = computed(() => appState.appsError)
  const busyById = computed(() => appState.busyById)
  const restartBusyById = computed(() => appState.restartBusyById)
  const bulkActionPending = ref('')
  const searchText = ref('')
  const storedCompactMode = localStorage.getItem(APPS_COMPACT_MODE_STORAGE_KEY)
  const compactMode = ref(storedCompactMode === null ? true : storedCompactMode === '1')
  const highlightedAppId = ref('')
  const searchDropdownVisible = ref(false)
  const activeSearchIndex = ref(-1)
  let highlightTimer = null

  const handlePointerDown = (event) => {
    const target = event?.target
      if (target instanceof Element) {
        if (!target.closest('.apps-search-box')) {
          searchDropdownVisible.value = false
          activeSearchIndex.value = -1
        }
        if (!target.closest('.apps-sort-box')) {
          appsSortDropdownVisible.value = false
        }
      }
    }

    const toggleSortDesc = () => {
      sortDesc.value = !sortDesc.value
      localStorage.setItem('APPS_SORT_DESC', sortDesc.value ? '1' : '0')
    }

    const setSortOption = (opt) => {
      if (sortOption.value === opt) {
        toggleSortDesc()
      } else {
        sortOption.value = opt
        sortDesc.value = opt === 'installed_at'
        localStorage.setItem('APPS_SORT_OPTION', opt)
        localStorage.setItem('APPS_SORT_DESC', sortDesc.value ? '1' : '0')
      }
      appsSortDropdownVisible.value = false
    }

    const searchResults = computed(() => {
      const keyword = String(searchText.value || '').trim().toLowerCase()
      if (!keyword) return []
      return apps.value
        .filter((app) => String(app?.name || app?.app_id || '').toLowerCase().includes(keyword))
        .slice(0, 20)
    })

  const uploadModal = useAppUploadInstallModal({
    async onInstalled() {
      await refresh()
    },
  })

  onMounted(() => {
    refresh()

    watch(
      () => route.path,
      (path) => {
        if (isAppsPollingRoute(path)) {
          startPolling()
          return
        }
        stopPolling()
      },
      { immediate: true },
    )

    if (isAppsPollingRoute(route.path) && String(route.query?.openUpload || '') === '1') {
      uploadModal.openUploadModal()
      const nextQuery = { ...route.query }
      delete nextQuery.openUpload
      router.replace({ path: route.path, query: nextQuery })
    }

    document.addEventListener('pointerdown', handlePointerDown)
  })

  onUnmounted(() => {
    stopPolling()
    document.removeEventListener('pointerdown', handlePointerDown)
    if (highlightTimer) {
      clearTimeout(highlightTimer)
      highlightTimer = null
    }
  })

  watch(
    () => searchText.value,
    (next) => {
      const hasKeyword = Boolean(String(next || '').trim())
      searchDropdownVisible.value = hasKeyword
      activeSearchIndex.value = hasKeyword && searchResults.value.length ? 0 : -1
    },
  )

  watch(
    () => compactMode.value,
    (next) => {
      localStorage.setItem(APPS_COMPACT_MODE_STORAGE_KEY, next ? '1' : '0')
    },
  )

  function jumpToAppCard(app) {
    const appId = String(app?.app_id || '')
    if (!appId) return
    const element = document.getElementById(`app-card-${appId}`)
    if (!element) return
    element.scrollIntoView({ behavior: 'smooth', block: 'center' })
    highlightedAppId.value = appId
    searchDropdownVisible.value = false
    activeSearchIndex.value = -1
    if (highlightTimer) {
      clearTimeout(highlightTimer)
    }
    highlightTimer = window.setTimeout(() => {
      highlightedAppId.value = ''
      highlightTimer = null
    }, 2200)
  }

  function openSearchDropdown() {
    if (!String(searchText.value || '').trim()) return
    searchDropdownVisible.value = true
    activeSearchIndex.value = searchResults.value.length ? 0 : -1
  }

  function closeSearchDropdown() {
    searchDropdownVisible.value = false
    activeSearchIndex.value = -1
  }

  function handleSearchKeydown(event) {
    if (!String(searchText.value || '').trim()) return

    if (event.key === 'ArrowDown') {
      event.preventDefault()
      if (!searchDropdownVisible.value) {
        openSearchDropdown()
        return
      }
      if (!searchResults.value.length) return
      activeSearchIndex.value = (activeSearchIndex.value + 1 + searchResults.value.length) % searchResults.value.length
      return
    }

    if (event.key === 'ArrowUp') {
      event.preventDefault()
      if (!searchDropdownVisible.value) {
        openSearchDropdown()
        return
      }
      if (!searchResults.value.length) return
      activeSearchIndex.value = (activeSearchIndex.value - 1 + searchResults.value.length) % searchResults.value.length
      return
    }

    if (event.key === 'Enter') {
      if (!searchDropdownVisible.value || !searchResults.value.length) return
      event.preventDefault()
      const target = searchResults.value[Math.max(0, activeSearchIndex.value)]
      if (target) {
        jumpToAppCard(target)
      }
      return
    }

    if (event.key === 'Escape') {
      if (!searchDropdownVisible.value) return
      event.preventDefault()
      closeSearchDropdown()
    }
  }

  function toggleCompactMode() {
    compactMode.value = !compactMode.value
  }

  function isFavoriteApp(app) {
    const appId = String(app?.app_id || '')
    return Boolean(appId && favoriteAppIdSet.value.has(appId))
  }

  function toggleFavoriteApp(app) {
    const appId = String(app?.app_id || '')
    if (!appId) return

    if (favoriteAppIdSet.value.has(appId)) {
      favoriteAppIds.value = favoriteAppIds.value.filter((item) => item !== appId)
    } else {
      favoriteAppIds.value = [...favoriteAppIds.value, appId]
    }
    writeFavoriteAppIds(favoriteAppIds.value)
  }

  async function runBulkAction(actionName, task) {
    appState.appsError = ''
    bulkActionPending.value = actionName
    try {
      await task()
      await refresh()
    } catch (err) {
      appState.appsError = String(err?.message || err || i18n.global.t('errors.operationFailed'))
    } finally {
      bulkActionPending.value = ''
    }
  }

  async function restartEnabledApps() {
    await runBulkAction('restartAutostart', async () => {
      await restartAutostartApps()
    })
  }

  async function startEnabledApps() {
    await runBulkAction('startAutostart', async () => {
      await startAutostartApps()
    })
  }

  async function stopEveryApp() {
    await runBulkAction('stopAll', async () => {
      await stopAllApps()
    })
  }

  return {
    apps,
    loading,
    error,
    busyById,
    restartBusyById,
    bulkActionPending,
    searchText,
    compactMode,
    favoriteAppIds,
    sortOption,
    sortDesc,
    appsSortDropdownVisible,
    setSortOption,
    toggleSortDesc,
    searchResults,
    searchDropdownVisible,
    activeSearchIndex,
    highlightedAppId,
    jumpToAppCard,
    openSearchDropdown,
    closeSearchDropdown,
    handleSearchKeydown,
    refresh,
    toggleCompactMode,
    isFavoriteApp,
    toggleFavoriteApp,
    toggleRunning,
    toggleAutostart,
    restartSingleApp,
    restartEnabledApps,
    startEnabledApps,
    stopEveryApp,
    ...uploadModal,
  }
}

import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import i18n from '../i18n'
import { appState, markGatewayOnline, patchApp, setAppDetail, setApps, setBusy } from '../state/appState'
import {
  fetchAppStatus,
  fetchInstalledApps,
  setAutostart,
  startApp,
  stopApp,
} from '../services/core/apps'
import { useAppUploadInstallModal } from './useAppUploadInstallModal'

let pollTimer = null

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

  const apps = computed(() => appState.apps)
  const loading = computed(() => appState.appsLoading)
  const error = computed(() => appState.appsError)
  const busyById = computed(() => appState.busyById)
  const searchText = ref('')
  const highlightedAppId = ref('')
  const searchDropdownVisible = ref(false)
  const activeSearchIndex = ref(-1)
  let highlightTimer = null

  const handlePointerDown = (event) => {
    const target = event?.target
    if (target instanceof Element && target.closest('.apps-search-box')) {
      return
    }
    searchDropdownVisible.value = false
    activeSearchIndex.value = -1
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

  return {
    apps,
    loading,
    error,
    busyById,
    searchText,
    searchResults,
    searchDropdownVisible,
    activeSearchIndex,
    highlightedAppId,
    jumpToAppCard,
    openSearchDropdown,
    closeSearchDropdown,
    handleSearchKeydown,
    refresh,
    toggleRunning,
    toggleAutostart,
    ...uploadModal,
  }
}

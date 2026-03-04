import { computed, onMounted, onUnmounted, ref } from 'vue'
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

export function useAppsPanel() {
  const route = useRoute()
  const router = useRouter()

  const apps = computed(() => appState.apps)
  const loading = computed(() => appState.appsLoading)
  const error = computed(() => appState.appsError)
  const busyById = computed(() => appState.busyById)

  const uploadModal = useAppUploadInstallModal({
    async onInstalled() {
      await refresh()
    },
  })

  onMounted(() => {
    refresh()
    startPolling()

    if (String(route.query?.openUpload || '') === '1') {
      uploadModal.openUploadModal()
      const nextQuery = { ...route.query }
      delete nextQuery.openUpload
      router.replace({ path: route.path, query: nextQuery })
    }
  })

  onUnmounted(() => {
    stopPolling()
  })

  return {
    apps,
    loading,
    error,
    busyById,
    refresh,
    toggleRunning,
    toggleAutostart,
    ...uploadModal,
  }
}

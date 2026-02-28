import { computed, onMounted, onUnmounted } from 'vue'
import { appState, markGatewayOnline, patchApp, setAppDetail, setApps, setBusy } from '../state/appState'
import { fetchAppStatus, fetchInstalledApps, setAutostart, startApp, stopApp } from '../services/core/apps'

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
    appState.appsError = String(err?.message || err || '加载失败')
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
    appState.appsError = String(err?.message || err || '操作失败')
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
    appState.appsError = String(err?.message || err || '操作失败')
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
  const apps = computed(() => appState.apps)
  const loading = computed(() => appState.appsLoading)
  const error = computed(() => appState.appsError)
  const busyById = computed(() => appState.busyById)

  onMounted(() => {
    refresh()
    startPolling()
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
  }
}

import { computed, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppsPanel } from './useAppsPanel'
import {
  fetchAppLogs,
  fetchAppVersions,
  switchAppVersion,
  uninstallApp,
  upgradeAppPackage,
} from '../services/core/apps'

export function useAppDetailPage() {
  const route = useRoute()
  const router = useRouter()

  const {
    apps,
    loading,
    error,
    refresh,
    busyById,
    toggleRunning,
    toggleAutostart,
  } = useAppsPanel()

  const app = computed(() => {
    const appId = String(route.params.appId || '')
    return apps.value.find((item) => item.app_id === appId) || null
  })

  const logText = ref('')
  const logOffset = ref(0)
  const logBusy = ref(false)
  const logError = ref('')

  const actionBusy = ref(false)
  const actionError = ref('')
  const actionMessage = ref('')

  const versions = ref([])
  const selectedVersion = ref('')
  const switchWithRestart = ref(true)

  const selectedFile = ref(null)
  const selectedFileName = ref('')

  const uninstallVersionOnly = ref(false)
  const uninstallPurge = ref(false)

  let logTimer = null

  const canSwitchVersion = computed(() => {
    return Boolean(
      app.value
      && selectedVersion.value
      && selectedVersion.value !== app.value.active_version,
    )
  })

  const canUpgrade = computed(() => Boolean(app.value && selectedFile.value && !actionBusy.value))

  const canUninstall = computed(() => Boolean(app.value && !actionBusy.value))

  function clearActionStatus() {
    actionError.value = ''
    actionMessage.value = ''
  }

  async function loadVersions(appId) {
    if (!appId) {
      versions.value = []
      selectedVersion.value = ''
      return
    }

    try {
      const data = await fetchAppVersions(appId)
      versions.value = Array.isArray(data?.versions) ? data.versions : []
      selectedVersion.value = data?.active_version || versions.value[0] || ''
    } catch {
      const fallbackVersions = Array.isArray(app.value?.versions) ? app.value.versions : []
      versions.value = fallbackVersions
      selectedVersion.value = app.value?.active_version || fallbackVersions[0] || ''
    }
  }

  async function loadLogs() {
    if (!app.value || logBusy.value) return
    logBusy.value = true
    try {
      const data = await fetchAppLogs(app.value.app_id, logOffset.value, 65536)
      if (data.reset) {
        logText.value = ''
      }
      if (data.chunk) {
        logText.value += data.chunk
        if (logText.value.length > 500000) {
          logText.value = logText.value.slice(-300000)
        }
      }
      logOffset.value = Number(data.next_offset || 0)
      logError.value = ''
    } catch (err) {
      logError.value = String(err?.message || err || '读取日志失败')
    } finally {
      logBusy.value = false
    }
  }

  function clearAndReloadLogs() {
    logText.value = ''
    logOffset.value = 0
    logError.value = ''
    loadLogs()
  }

  function onUpgradeFileChange(fileList) {
    const file = fileList?.[0] || null
    selectedFile.value = file
    selectedFileName.value = file?.name || ''
    clearActionStatus()
  }

  async function runUpgrade() {
    if (!app.value || !selectedFile.value) return
    actionBusy.value = true
    clearActionStatus()
    try {
      await upgradeAppPackage(app.value.app_id, selectedFile.value)
      selectedFile.value = null
      selectedFileName.value = ''
      await refresh()
      await loadVersions(app.value.app_id)
      clearAndReloadLogs()
      actionMessage.value = '上传并升级成功'
    } catch (err) {
      actionError.value = String(err?.message || err || '升级失败')
    } finally {
      actionBusy.value = false
    }
  }

  async function runSwitchVersion() {
    if (!app.value || !canSwitchVersion.value) return
    actionBusy.value = true
    clearActionStatus()
    try {
      await switchAppVersion(app.value.app_id, selectedVersion.value, switchWithRestart.value)
      await refresh()
      await loadVersions(app.value.app_id)
      clearAndReloadLogs()
      actionMessage.value = '版本切换成功'
    } catch (err) {
      actionError.value = String(err?.message || err || '切换版本失败')
    } finally {
      actionBusy.value = false
    }
  }

  async function runUninstall() {
    if (!app.value) return

    const allVersions = Array.isArray(versions.value) && versions.value.length
      ? versions.value
      : (Array.isArray(app.value.versions) ? app.value.versions : [])
    const isLastVersion = allVersions.length <= 1

    let uninstallVersion = uninstallVersionOnly.value ? app.value.active_version || null : null

    if (uninstallVersionOnly.value && isLastVersion) {
      const confirmedAsWholeApp = confirmLastVersionUninstallAsWholeApp(app.value.app_id)
      if (!confirmedAsWholeApp) return
      uninstallVersion = null
    } else if (!uninstallVersionOnly.value) {
      const confirmedWholeApp = confirmWholeAppUninstall(app.value.app_id)
      if (!confirmedWholeApp) return
    } else {
      const confirmedVersionOnly = window.confirm(
        `确认卸载当前版本 ${app.value.active_version || '-'} 吗？`,
      )
      if (!confirmedVersionOnly) return
    }

    actionBusy.value = true
    clearActionStatus()
    try {
      await uninstallApp(app.value.app_id, {
        version: uninstallVersion,
        purge: uninstallPurge.value,
      })
      await refresh()
      if (uninstallVersion) {
        await loadVersions(app.value.app_id)
        actionMessage.value = '卸载当前版本成功'
      } else {
        router.push('/dashboard/apps')
      }
    } catch (err) {
      actionError.value = String(err?.message || err || '卸载失败')
    } finally {
      actionBusy.value = false
    }
  }

  function startLogPolling() {
    if (logTimer) return
    logTimer = setInterval(() => {
      loadLogs()
    }, 2000)
  }

  function stopLogPolling() {
    if (!logTimer) return
    clearInterval(logTimer)
    logTimer = null
  }

  watch(
    () => route.params.appId,
    (appId) => {
      clearActionStatus()
      selectedFile.value = null
      selectedFileName.value = ''
      uninstallVersionOnly.value = false
      uninstallPurge.value = false
      clearAndReloadLogs()
      loadVersions(String(appId || ''))
    },
    { immediate: true },
  )

  watch(
    app,
    (value) => {
      if (value) {
        startLogPolling()
        return
      }
      stopLogPolling()
    },
    { immediate: true },
  )

  onUnmounted(() => {
    stopLogPolling()
  })

  function backToList() {
    router.push('/dashboard/apps')
  }

  function confirmWholeAppUninstall(appId) {
    const first = window.confirm(
      `将卸载整个应用 ${appId}（包含所有版本）。确认继续吗？`,
    )
    if (!first) return false

    return window.confirm(
      '再次确认：这是不可逆操作，应用及其版本都会被移除。确定执行吗？',
    )
  }

  function confirmLastVersionUninstallAsWholeApp(appId) {
    const first = window.confirm(
      '你选择的是“仅卸载当前版本”，但当前已是最后一个版本。\n继续将等同于卸载整个应用。是否继续？',
    )
    if (!first) return false

    return window.confirm(
      `最终确认：将卸载整个应用 ${appId}。确定执行吗？`,
    )
  }

  return {
    app,
    loading,
    error,
    refresh,
    busyById,
    toggleRunning,
    toggleAutostart,
    logText,
    logBusy,
    logError,
    loadLogs,
    clearAndReloadLogs,
    actionBusy,
    actionError,
    actionMessage,
    versions,
    selectedVersion,
    switchWithRestart,
    canSwitchVersion,
    onUpgradeFileChange,
    selectedFileName,
    canUpgrade,
    runUpgrade,
    runSwitchVersion,
    uninstallVersionOnly,
    uninstallPurge,
    canUninstall,
    runUninstall,
    backToList,
  }
}

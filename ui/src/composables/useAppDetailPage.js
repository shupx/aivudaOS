import { computed, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAppsPanel } from './useAppsPanel'
import {
  fetchAppLogs,
  fetchAppVersions,
  subscribeAppOperationEvents,
  switchAppVersion,
  uninstallApp,
  updateAppThisVersion,
} from '../services/core/apps'

export function useAppDetailPage() {
  const { t } = useI18n()
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
  const actionLiveStatus = ref('')
  const actionLiveStatusDone = ref(false)
  const actionLiveOutput = ref('')
  const showActionOutputModal = ref(false)

  const versions = ref([])
  const selectedVersion = ref('')
  const switchWithRestart = ref(true)

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

  const canUninstall = computed(() => Boolean(app.value && !actionBusy.value))

  function clearActionStatus() {
    actionError.value = ''
    actionMessage.value = ''
    actionLiveStatus.value = ''
    actionLiveStatusDone.value = false
    actionLiveOutput.value = ''
  }

  function closeActionOutputModal() {
    showActionOutputModal.value = false
  }

  function appendActionLine(line) {
    if (!line) return
    actionLiveOutput.value += `${line}\n`
    if (actionLiveOutput.value.length > 250000) {
      actionLiveOutput.value = actionLiveOutput.value.slice(-150000)
    }
  }

  function waitForOperation(operationId) {
    return new Promise((resolve, reject) => {
      let settled = false
      const subscription = subscribeAppOperationEvents(operationId, {
        onEvent(event) {
          if (!event || typeof event !== 'object') return

          if (event.type === 'status') {
            actionLiveStatus.value = event.message || event.phase || event.status || actionLiveStatus.value
          }
          if (event.type === 'log') {
            appendActionLine(event.line || '')
          }
          if (event.type === 'error') {
            appendActionLine(event.message || t('apps.operationFailed'))
            actionError.value = event.message || t('apps.operationFailed')
            actionLiveStatusDone.value = false
          }
          if (event.type === 'completed') {
            if (settled) return
            settled = true
            subscription.close()
            if (event.status === 'completed') {
              actionLiveStatusDone.value = true
              resolve(event.result || {})
            } else {
              actionLiveStatusDone.value = false
              reject(new Error(event.error || event.message || t('appDetail.operationFailed')))
            }
          }
        },
        onError(err) {
          if (settled) return
          settled = true
          subscription.close()
          reject(err)
        },
      })
    })
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
      logError.value = String(err?.message || err || t('appDetail.readLogsFailed'))
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

  function goToManualUpload() {
    router.push({
      path: '/dashboard/apps',
      query: { openUpload: '1' },
    })
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
      actionMessage.value = t('appDetail.switchSuccess')
    } catch (err) {
      actionError.value = String(err?.message || err || t('appDetail.switchFailed'))
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
        t('appDetail.uninstallVersionConfirm', { version: app.value.active_version || '-' }),
      )
      if (!confirmedVersionOnly) return
    }

    actionBusy.value = true
    clearActionStatus()
    actionLiveStatus.value = t('appDetail.queued')
    showActionOutputModal.value = true
    try {
      const operation = await uninstallApp(app.value.app_id, {
        version: uninstallVersion,
        purge: uninstallPurge.value,
      })
      await waitForOperation(operation.operation_id)
      await refresh()
      if (uninstallVersion) {
        await loadVersions(app.value.app_id)
        actionMessage.value = t('appDetail.uninstallCurrentSuccess')
      } else {
        router.push('/dashboard/apps')
      }
    } catch (err) {
      actionError.value = String(err?.message || err || t('appDetail.uninstallFailed'))
    } finally {
      actionBusy.value = false
    }
  }

  async function runUpdateThisVersionScript() {
    if (!app.value || !selectedVersion.value) return
    const confirmed = window.confirm(
      t('appDetail.updateThisVersionConfirm', { version: selectedVersion.value }),
    )
    if (!confirmed) return

    actionBusy.value = true
    clearActionStatus()
    actionLiveStatus.value = t('appDetail.queued')
    showActionOutputModal.value = true
    try {
      const operation = await updateAppThisVersion(app.value.app_id, selectedVersion.value)
      await waitForOperation(operation.operation_id)
      actionMessage.value = t('appDetail.updateScriptSuccess')
    } catch (err) {
      actionError.value = String(err?.message || err || t('appDetail.updateScriptFailed'))
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
      t('appDetail.uninstallWholeFirst', { appId }),
    )
    if (!first) return false

    return window.confirm(
      t('appDetail.uninstallWholeSecond'),
    )
  }

  function confirmLastVersionUninstallAsWholeApp(appId) {
    const first = window.confirm(
      t('appDetail.uninstallLastVersionFirst'),
    )
    if (!first) return false

    return window.confirm(
      t('appDetail.uninstallLastVersionSecond', { appId }),
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
    actionLiveStatus,
    actionLiveStatusDone,
    actionLiveOutput,
    showActionOutputModal,
    closeActionOutputModal,
    versions,
    selectedVersion,
    switchWithRestart,
    canSwitchVersion,
    goToManualUpload,
    runUpdateThisVersionScript,
    runSwitchVersion,
    uninstallVersionOnly,
    uninstallPurge,
    canUninstall,
    runUninstall,
    backToList,
  }
}

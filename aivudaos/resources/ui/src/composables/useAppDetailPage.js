import { computed, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAppsPanel } from './useAppsPanel'
import {
  cancelAppOperation,
  fetchAppLogs,
  fetchAppVersions,
  openAppOperationInteractiveSocket,
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
    restartBusyById,
    toggleRunning,
    toggleAutostart,
    restartSingleApp,
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
  const actionCancelBusy = ref(false)
  const currentActionOperationId = ref('')
  const actionInteractiveInput = ref('')
  const actionInteractiveReady = ref(false)
  const actionInteractiveMaskInput = ref(true)
  let actionInteractiveSubmitHandler = null

  const versions = ref([])
  const selectedVersion = ref('')
  const switchWithRestart = ref(true)

  const uninstallVersionOnly = ref(true)
  const uninstallPurge = ref(true)

  let logTimer = null

  function normalizeOutputText(value) {
    return String(value || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  }

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
    if (actionBusy.value) return
    showActionOutputModal.value = false
  }

  function setActionInteractiveInput(value) {
    actionInteractiveInput.value = String(value || '')
  }

  function setActionInteractiveMaskInput(value) {
    actionInteractiveMaskInput.value = Boolean(value)
  }

  function submitActionInteractiveInput() {
    if (typeof actionInteractiveSubmitHandler === 'function') {
      actionInteractiveSubmitHandler()
      return
    }
    actionError.value = t('apps.interactiveNotReadyWithProxyHint')
  }

  function appendActionLine(line) {
    if (line === undefined || line === null) return
    actionLiveOutput.value += normalizeOutputText(line)
    if (actionLiveOutput.value.length > 250000) {
      actionLiveOutput.value = actionLiveOutput.value.slice(-150000)
    }
  }

  function appendActionChunk(chunk) {
    if (!chunk) return
    actionLiveOutput.value += normalizeOutputText(chunk)
    if (actionLiveOutput.value.length > 250000) {
      actionLiveOutput.value = actionLiveOutput.value.slice(-150000)
    }
  }

  function waitForOperation(operationId) {
    return new Promise((resolve, reject) => {
      let settled = false
      let interactiveSocket = null
      const handledConfirmSeq = new Set()

      function finish(callback) {
        if (settled) return
        settled = true
        if (interactiveSocket) {
          interactiveSocket.close()
          interactiveSocket = null
        }
        actionInteractiveReady.value = false
        actionCancelBusy.value = false
        currentActionOperationId.value = ''
        actionInteractiveSubmitHandler = null
        subscription.close()
        callback()
      }

      function sendInteractiveInput() {
        const value = String(actionInteractiveInput.value || '')
        if (!value) return
        if (!interactiveSocket || !interactiveSocket.isOpen()) {
          actionError.value = t('apps.interactiveNotReadyWithProxyHint')
          return
        }
        try {
          interactiveSocket.sendInput(value)
          actionInteractiveInput.value = ''
          actionError.value = ''
        } catch (err) {
          actionError.value = String(err?.message || err || t('apps.interactiveSendFailed'))
        }
      }

      actionInteractiveSubmitHandler = sendInteractiveInput

      interactiveSocket = openAppOperationInteractiveSocket(operationId, {
        onOpen() {
          actionInteractiveReady.value = true
        },
        onClose() {
          actionInteractiveReady.value = false
        },
        onMessage(payload) {
          if (payload?.type === 'interactive_closed') {
            actionInteractiveReady.value = false
          }
        },
        onError(err) {
          actionInteractiveReady.value = false
          appendActionLine(`${t('apps.interactiveConnectionError')}: ${String(err?.message || err || '')}\n`)
        },
      })

      const subscription = subscribeAppOperationEvents(operationId, {
        onEvent(event) {
          if (!event || typeof event !== 'object') return

          if (event.type === 'status') {
            actionLiveStatus.value = event.message || event.phase || event.status || actionLiveStatus.value

            if (
              event.phase === 'pre_uninstall'
              && event.status === 'awaiting_confirmation'
              && !handledConfirmSeq.has(Number(event.seq || 0))
            ) {
              handledConfirmSeq.add(Number(event.seq || 0))
              const confirmed = window.confirm(
                t('appDetail.uninstallHookFailedContinueConfirm', {
                  error: event.error || '-',
                }),
              )
              if (interactiveSocket && interactiveSocket.isOpen()) {
                try {
                  interactiveSocket.sendInput(confirmed ? 'y' : 'n')
                } catch (err) {
                  actionError.value = String(err?.message || err || t('apps.interactiveSendFailed'))
                }
              }
            }
          }
          if (event.type === 'log') {
            if (typeof event.chunk === 'string') {
              appendActionChunk(event.chunk)
            } else {
              appendActionLine(typeof event.line === 'string' ? event.line : `${event.line || ''}\n`)
            }
          }
          if (event.type === 'error') {
            appendActionLine(`${event.message || t('apps.operationFailed')}\n`)
            actionError.value = event.message || t('apps.operationFailed')
            actionLiveStatusDone.value = false
          }
          if (event.type === 'completed') {
            if (event.status === 'completed') {
              finish(() => {
                actionLiveStatusDone.value = true
                resolve(event.result || {})
              })
            } else {
              finish(() => {
                actionLiveStatusDone.value = false
                reject(new Error(event.error || event.message || t('appDetail.operationFailed')))
              })
            }
          }
        },
        onError(err) {
          finish(() => {
            reject(err)
          })
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

  function goToConfigPage() {
    if (!app.value) return
    router.push({
      path: '/dashboard/apps/configs',
      query: { app_id: app.value.app_id },
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
    currentActionOperationId.value = ''
    actionCancelBusy.value = false
    actionInteractiveInput.value = ''
    actionInteractiveReady.value = false
    actionInteractiveMaskInput.value = true
    try {
      const operation = await uninstallApp(app.value.app_id, {
        version: uninstallVersion,
        purge: uninstallPurge.value,
      })
      currentActionOperationId.value = String(operation?.operation_id || '')
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
    currentActionOperationId.value = ''
    actionCancelBusy.value = false
    actionInteractiveInput.value = ''
    actionInteractiveReady.value = false
    actionInteractiveMaskInput.value = true
    try {
      const operation = await updateAppThisVersion(app.value.app_id, selectedVersion.value)
      currentActionOperationId.value = String(operation?.operation_id || '')
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
      uninstallVersionOnly.value = true
      uninstallPurge.value = true
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
    actionInteractiveSubmitHandler = null
  })

  function backToList() {
    router.push('/dashboard/apps')
  }

  async function cancelCurrentAction() {
    if (!actionBusy.value) return
    if (actionCancelBusy.value) return

    const operationId = String(currentActionOperationId.value || '')
    if (!operationId) {
      actionError.value = t('apps.interactiveNotReadyWithProxyHint')
      return
    }

    actionCancelBusy.value = true
    try {
      await cancelAppOperation(operationId)
      actionLiveStatus.value = t('apps.cancelling')
      actionError.value = ''
    } catch (err) {
      actionError.value = String(err?.message || err || t('apps.cancelFailed'))
    } finally {
      actionCancelBusy.value = false
    }
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
    restartBusyById,
    toggleRunning,
    toggleAutostart,
    restartSingleApp,
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
    actionCancelBusy,
    closeActionOutputModal,
    cancelCurrentAction,
    actionInteractiveInput,
    actionInteractiveReady,
    actionInteractiveMaskInput,
    setActionInteractiveInput,
    setActionInteractiveMaskInput,
    submitActionInteractiveInput,
    versions,
    selectedVersion,
    switchWithRestart,
    canSwitchVersion,
    goToManualUpload,
    goToConfigPage,
    runUpdateThisVersionScript,
    runSwitchVersion,
    uninstallVersionOnly,
    uninstallPurge,
    canUninstall,
    runUninstall,
    backToList,
  }
}

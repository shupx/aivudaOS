import { computed, onMounted, onUnmounted, ref } from 'vue'
import { appState, markGatewayOnline, patchApp, setAppDetail, setApps, setBusy } from '../state/appState'
import {
  fetchAppStatus,
  fetchInstalledApps,
  setAutostart,
  subscribeAppOperationEvents,
  startApp,
  stopApp,
  uploadAppPackage,
} from '../services/core/apps'

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

  const showUploadModal = ref(false)
  const uploadBusy = ref(false)
  const uploadError = ref('')
  const uploadStatus = ref('')
  const uploadOutput = ref('')
  const uploadFile = ref(null)
  const uploadFileName = ref('')

  function openUploadModal() {
    uploadError.value = ''
    showUploadModal.value = true
  }

  function closeUploadModal() {
    if (uploadBusy.value) return
    showUploadModal.value = false
    uploadError.value = ''
    uploadStatus.value = ''
    uploadOutput.value = ''
    uploadFile.value = null
    uploadFileName.value = ''
  }

  function onUploadFileChange(fileList) {
    const file = fileList?.[0] || null
    uploadFile.value = file
    uploadFileName.value = file?.name || ''
    uploadError.value = ''
  }

  async function submitUpload() {
    if (!uploadFile.value || uploadBusy.value) return
    uploadBusy.value = true
    uploadError.value = ''
    uploadStatus.value = '任务已提交'
    uploadOutput.value = ''
    try {
      const operation = await uploadAppPackage(uploadFile.value)
      await waitForOperation(operation.operation_id)
      await refresh()
      uploadStatus.value = '安装完成'
      uploadFile.value = null
      uploadFileName.value = ''
    } catch (err) {
      uploadError.value = String(err?.message || err || '上传失败')
    } finally {
      uploadBusy.value = false
    }
  }

  function appendUploadLine(line) {
    if (!line) return
    uploadOutput.value += `${line}\n`
    if (uploadOutput.value.length > 200000) {
      uploadOutput.value = uploadOutput.value.slice(-120000)
    }
  }

  function waitForOperation(operationId) {
    return new Promise((resolve, reject) => {
      let settled = false
      const subscription = subscribeAppOperationEvents(operationId, {
        onEvent(event) {
          if (!event || typeof event !== 'object') return

          if (event.type === 'status') {
            uploadStatus.value = event.message || event.phase || event.status || uploadStatus.value
          }
          if (event.type === 'log') {
            appendUploadLine(event.line || '')
          }
          if (event.type === 'error') {
            appendUploadLine(event.message || '执行失败')
            uploadError.value = event.message || '执行失败'
          }
          if (event.type === 'completed') {
            if (settled) return
            settled = true
            subscription.close()
            if (event.status === 'completed') {
              uploadStatus.value = '安装完成'
              resolve(event.result || {})
            } else {
              reject(new Error(event.error || event.message || '安装失败'))
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
    showUploadModal,
    uploadBusy,
    uploadError,
    uploadStatus,
    uploadOutput,
    uploadFileName,
    openUploadModal,
    closeUploadModal,
    onUploadFileChange,
    submitUpload,
  }
}

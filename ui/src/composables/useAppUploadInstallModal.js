import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  cancelAppOperation,
  fetchAppOperation,
  openAppOperationInteractiveSocket,
  subscribeAppOperationEvents,
  uploadAppPackage,
} from '../services/core/apps'

export function useAppUploadInstallModal({ onInstalled } = {}) {
  const { t } = useI18n()

  const showUploadModal = ref(false)
  const uploadBusy = ref(false)
  const uploadError = ref('')
  const uploadStatus = ref('')
  const uploadStatusDone = ref(false)
  const uploadOutput = ref('')
  const uploadFile = ref(null)
  const uploadFileName = ref('')
  const uploadHint = ref('')
  const uploadShowFilePicker = ref(true)
  const uploadInteractiveInput = ref('')
  const uploadInteractiveReady = ref(false)
  const uploadInteractiveMaskInput = ref(true)
  const uploadCancelBusy = ref(false)
  const currentOperationId = ref('')
  let interactiveSubmitHandler = null

  function openUploadModal({ hint = '', showFilePicker = true } = {}) {
    uploadError.value = ''
    uploadStatusDone.value = false
    uploadHint.value = String(hint || '')
    uploadShowFilePicker.value = Boolean(showFilePicker)
    showUploadModal.value = true
  }

  function closeUploadModal() {
    if (uploadBusy.value) return
    showUploadModal.value = false
    uploadError.value = ''
    uploadStatus.value = ''
    uploadStatusDone.value = false
    uploadOutput.value = ''
    uploadFile.value = null
    uploadFileName.value = ''
    uploadHint.value = ''
    uploadShowFilePicker.value = true
    uploadInteractiveInput.value = ''
    uploadInteractiveReady.value = false
    uploadInteractiveMaskInput.value = true
    uploadCancelBusy.value = false
    currentOperationId.value = ''
    interactiveSubmitHandler = null
  }

  function setUploadFile(file) {
    const nextFile = file || null
    uploadFile.value = nextFile
    uploadFileName.value = nextFile?.name || ''
    uploadError.value = ''
  }

  function onUploadFileChange(fileList) {
    setUploadFile(fileList?.[0] || null)
  }

  function appendUploadLine(line) {
    if (!line) return
    uploadOutput.value += line
    if (uploadOutput.value.length > 200000) {
      uploadOutput.value = uploadOutput.value.slice(-120000)
    }
  }

  function appendUploadChunk(chunk) {
    if (!chunk) return
    uploadOutput.value += chunk
    if (uploadOutput.value.length > 200000) {
      uploadOutput.value = uploadOutput.value.slice(-120000)
    }
  }

  function waitForOperation(operationId) {
    return new Promise((resolve, reject) => {
      let settled = false
      let interactiveSocket = null
      let pollTimer = null
      let pollBusy = false
      let pollWarned = false
      let sseWarned = false

      const finish = (callback) => {
        if (settled) return
        settled = true
        if (pollTimer) {
          clearInterval(pollTimer)
          pollTimer = null
        }
        if (interactiveSocket) {
          interactiveSocket.close()
          interactiveSocket = null
        }
        uploadInteractiveReady.value = false
        uploadCancelBusy.value = false
        currentOperationId.value = ''
        interactiveSubmitHandler = null
        subscription.close()
        callback()
      }

      function sendInteractiveInput() {
        const value = String(uploadInteractiveInput.value || '')
        if (!value) return
        if (!interactiveSocket || !interactiveSocket.isOpen()) {
          uploadError.value = t('apps.interactiveNotReady')
          return
        }
        try {
          interactiveSocket.sendInput(value)
          uploadInteractiveInput.value = ''
          uploadError.value = ''
        } catch (err) {
          uploadError.value = String(err?.message || err || t('apps.interactiveSendFailed'))
        }
      }

      interactiveSubmitHandler = sendInteractiveInput

      async function pollOperationState() {
        if (settled || pollBusy) return
        pollBusy = true
        try {
          const info = await fetchAppOperation(operationId)
          const status = String(info?.status || '')
          if (status) {
            uploadStatus.value = status
          }
          if (status === 'completed') {
            finish(() => {
              uploadStatus.value = t('apps.installed')
              uploadStatusDone.value = true
              resolve(info?.result || {})
            })
            return
          }
          if (status === 'failed' || status === 'canceled') {
            const message = String(info?.error || t('apps.installFailed'))
            finish(() => {
              uploadStatusDone.value = false
              reject(new Error(message))
            })
          }
        } catch (err) {
          if (!pollWarned) {
            pollWarned = true
            appendUploadLine(`${t('apps.realtimeConnectionError')}: ${String(err?.message || err || '')}\n`)
          }
        } finally {
          pollBusy = false
        }
      }

      function ensurePolling() {
        if (pollTimer || settled) return
        pollTimer = setInterval(() => {
          pollOperationState()
        }, 1000)
        pollOperationState()
      }

      interactiveSocket = openAppOperationInteractiveSocket(operationId, {
        onOpen() {
          uploadInteractiveReady.value = true
        },
        onClose() {
          uploadInteractiveReady.value = false
        },
        onMessage(payload) {
          if (payload?.type === 'interactive_closed') {
            uploadInteractiveReady.value = false
          }
        },
        onError(err) {
          uploadInteractiveReady.value = false
          appendUploadLine(`${t('apps.interactiveConnectionError')}: ${String(err?.message || err || '')}\n`)
        },
      })

      const subscription = subscribeAppOperationEvents(operationId, {
        onEvent(event) {
          if (!event || typeof event !== 'object') return

          if (event.type === 'status') {
            uploadStatus.value = event.message || event.phase || event.status || uploadStatus.value
          }
          if (event.type === 'log') {
            if (typeof event.chunk === 'string') {
              appendUploadChunk(event.chunk)
            } else {
              appendUploadLine(`${event.line || ''}\n`)
            }
          }
          if (event.type === 'error') {
            appendUploadLine(event.message || t('apps.operationFailed'))
            uploadError.value = event.message || t('apps.operationFailed')
            uploadStatusDone.value = false
          }
          if (event.type === 'completed') {
            if (event.status === 'completed') {
              finish(() => {
                uploadStatus.value = t('apps.installed')
                uploadStatusDone.value = true
                resolve(event.result || {})
              })
            } else {
              finish(() => {
                uploadStatusDone.value = false
                reject(new Error(event.error || event.message || uploadError.value || t('apps.installFailed')))
              })
            }
          }
        },
        onError(err) {
          if (settled) return
          if (!sseWarned) {
            sseWarned = true
            appendUploadLine(`${t('apps.realtimeConnectionError')}: ${String(err?.message || err || '')}\n`)
          }
          ensurePolling()
        },
      })

    })
  }

  async function submitUpload() {
    if (!uploadFile.value || uploadBusy.value) return
    uploadBusy.value = true
    uploadError.value = ''
    uploadStatus.value = t('apps.taskQueued')
    uploadStatusDone.value = false
    uploadOutput.value = ''
    try {
      const operation = await uploadAppPackage(uploadFile.value, { overwrite: false })
      currentOperationId.value = String(operation?.operation_id || '')
      uploadInteractiveReady.value = false
      await waitForOperation(operation.operation_id)
      if (onInstalled) {
        await onInstalled(operation)
      }
      uploadStatus.value = t('apps.installed')
      uploadStatusDone.value = true
      uploadFile.value = null
      uploadFileName.value = ''
    } catch (err) {
      const message = String(err?.message || err || t('apps.uploadFailed'))
      const isOverwriteConflict = /(already installed|version already installed|已安装|同版本)/i.test(message)
      if (!isOverwriteConflict) {
        uploadError.value = message
        return
      }

      const shouldOverwrite = window.confirm(t('apps.overwriteConfirm'))
      if (!shouldOverwrite) {
        uploadError.value = t('apps.overwriteCanceled')
        return
      }

      const shouldOverwriteAgain = window.confirm(t('apps.overwriteConfirmSecond'))
      if (!shouldOverwriteAgain) {
        uploadError.value = t('apps.overwriteCanceled')
        return
      }

      try {
        uploadStatus.value = t('apps.overwriting')
        uploadStatusDone.value = false
        uploadOutput.value = ''
        const overwriteOperation = await uploadAppPackage(uploadFile.value, { overwrite: true })
        currentOperationId.value = String(overwriteOperation?.operation_id || '')
        uploadInteractiveReady.value = false
        await waitForOperation(overwriteOperation.operation_id)
        if (onInstalled) {
          await onInstalled(overwriteOperation)
        }
        uploadStatus.value = t('apps.installed')
        uploadStatusDone.value = true
        uploadFile.value = null
        uploadFileName.value = ''
        uploadError.value = ''
      } catch (overwriteErr) {
        uploadError.value = String(overwriteErr?.message || overwriteErr || t('apps.uploadFailed'))
      }
    } finally {
      uploadBusy.value = false
    }
  }

  return {
    showUploadModal,
    uploadBusy,
    uploadError,
    uploadStatus,
    uploadStatusDone,
    uploadOutput,
    uploadFileName,
    uploadHint,
    uploadShowFilePicker,
    uploadInteractiveInput,
    uploadInteractiveReady,
    uploadInteractiveMaskInput,
    uploadCancelBusy,
    openUploadModal,
    closeUploadModal,
    setUploadFile,
    onUploadFileChange,
    submitUpload,
    async cancelCurrentUpload() {
      if (!uploadBusy.value) return
      if (uploadCancelBusy.value) return
      const operationId = String(currentOperationId.value || '')
      if (!operationId) {
        uploadError.value = t('apps.interactiveNotReady')
        return
      }
      uploadCancelBusy.value = true
      try {
        await cancelAppOperation(operationId)
        uploadStatus.value = t('apps.cancelling')
      } catch (err) {
        uploadError.value = String(err?.message || err || t('apps.cancelFailed'))
      } finally {
        uploadCancelBusy.value = false
      }
    },
    submitInteractiveInput() {
      if (typeof interactiveSubmitHandler === 'function') {
        interactiveSubmitHandler()
        return
      }
      uploadError.value = t('apps.interactiveNotReady')
    },
    setInteractiveInput(value) {
      uploadInteractiveInput.value = String(value || '')
    },
    setInteractiveMaskInput(value) {
      uploadInteractiveMaskInput.value = Boolean(value)
    },
  }
}

import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { subscribeAppOperationEvents, uploadAppPackage } from '../services/core/apps'

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
    uploadOutput.value += `${line}\n`
    if (uploadOutput.value.length > 200000) {
      uploadOutput.value = uploadOutput.value.slice(-120000)
    }
  }

  function waitForOperation(operationId) {
    return new Promise((resolve, reject) => {
      let settled = false
      let transportErrorTimer = null

      const finish = (callback) => {
        if (settled) return
        settled = true
        if (transportErrorTimer) {
          clearTimeout(transportErrorTimer)
          transportErrorTimer = null
        }
        subscription.close()
        callback()
      }

      const subscription = subscribeAppOperationEvents(operationId, {
        onEvent(event) {
          if (!event || typeof event !== 'object') return
          if (transportErrorTimer) {
            clearTimeout(transportErrorTimer)
            transportErrorTimer = null
          }

          if (event.type === 'status') {
            uploadStatus.value = event.message || event.phase || event.status || uploadStatus.value
          }
          if (event.type === 'log') {
            appendUploadLine(event.line || '')
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
          if (transportErrorTimer) return
          transportErrorTimer = setTimeout(() => {
            finish(() => {
              reject(err)
            })
          }, 800)
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
    openUploadModal,
    closeUploadModal,
    setUploadFile,
    onUploadFileChange,
    submitUpload,
  }
}

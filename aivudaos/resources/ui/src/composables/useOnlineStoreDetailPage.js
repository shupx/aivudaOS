import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { resolveAppStoreBaseUrl } from '../services/core/config'
import {
  MAX_IN_MEMORY_INSTALL_BYTES,
  downloadStorePackageByBrowser,
  downloadStorePackageForInstall,
  fetchStoreAppDetail,
} from '../services/core/store'
import { useAppUploadInstallModal } from './useAppUploadInstallModal'
import { useStoreDisplayFormat } from './useStoreDisplayFormat'

export function useOnlineStoreDetailPage() {
  const { t } = useI18n()
  const { formatStoreUpdatedAt, formatStorePackageSize } = useStoreDisplayFormat()
  const route = useRoute()
  const router = useRouter()

  const loading = ref(false)
  const error = ref('')
  const actionError = ref('')
  const actionMessage = ref('')

  const appId = computed(() => String(route.params.appId || ''))
  const storeBaseUrl = ref('')
  const appInfo = ref(null)
  const versions = ref([])

  const actingByVersion = ref({})
  const localDownloadingByVersion = ref({})
  const downloadProgressByVersion = ref({})

  const uploadModal = useAppUploadInstallModal({
    async onInstalled() {
      actionMessage.value = t('store.installCompleted')
    },
  })

  function setActing(version, busy) {
    actingByVersion.value = {
      ...actingByVersion.value,
      [version]: Boolean(busy),
    }
  }

  function setDownloadProgress(version, percent) {
    downloadProgressByVersion.value = {
      ...downloadProgressByVersion.value,
      [version]: Math.max(0, Math.min(100, Number(percent) || 0)),
    }
  }

  function setLocalDownloading(version, busy) {
    localDownloadingByVersion.value = {
      ...localDownloadingByVersion.value,
      [version]: Boolean(busy),
    }
  }

  async function load() {
    loading.value = true
    error.value = ''
    actionError.value = ''
    actionMessage.value = ''
    try {
      const baseUrl = resolveAppStoreBaseUrl()
      storeBaseUrl.value = baseUrl

      const detail = await fetchStoreAppDetail(baseUrl, appId.value)
      appInfo.value = detail?.app || null
      versions.value = Array.isArray(detail?.versions)
        ? detail.versions
          .filter((item) => item?.status === 'published')
          .map((item) => ({
            ...item,
            updated_at_display: formatStoreUpdatedAt(item?.updated_at),
            artifact_size_display: formatStorePackageSize(item?.artifact_size),
          }))
        : []
    } catch (err) {
      error.value = String(err?.message || err || t('store.loadFailed'))
    } finally {
      loading.value = false
    }
  }

  async function downloadAndInstallVersion(version) {
    if (!version || actingByVersion.value[version]) return
    setActing(version, true)
    actionError.value = ''
    actionMessage.value = ''
    try {
      const result = await downloadStorePackageForInstall(
        storeBaseUrl.value,
        appId.value,
        version,
        {
          onProgress(progress) {
            setDownloadProgress(version, progress.percent)
          },
        },
      )

      if (result.mode === 'auto') {
        actionMessage.value = t('store.downloadPrepared', { version })
        uploadModal.setUploadFile(result.file)
        uploadModal.openUploadModal({
          hint: t('store.installAutoSelected', { filename: result.filename }),
          showFilePicker: false,
        })
        await Promise.resolve()
        await uploadModal.submitUpload()
      } else {
        actionMessage.value = t('store.downloadTriggered', { version })
        const sizeLimitMb = Math.floor(MAX_IN_MEMORY_INSTALL_BYTES / (1024 * 1024))
        const shouldInstallNow = window.confirm(
          t('store.installNowManualConfirm', { version, sizeLimitMb }),
        )
        if (shouldInstallNow) {
          uploadModal.openUploadModal({
            hint: t('store.installSelectDownloaded', { filename: result.filename }),
          })
        }
      }
    } catch (err) {
      actionError.value = String(err?.message || err || t('store.downloadFailed'))
    } finally {
      setDownloadProgress(version, 0)
      setActing(version, false)
    }
  }

  async function downloadPackageToLocal(version) {
    if (!version || localDownloadingByVersion.value[version]) return
    setLocalDownloading(version, true)
    actionError.value = ''
    actionMessage.value = ''
    try {
      await downloadStorePackageByBrowser(storeBaseUrl.value, appId.value, version)
      actionMessage.value = t('store.downloadTriggered', { version })
    } catch (err) {
      actionError.value = String(err?.message || err || t('store.downloadFailed'))
    } finally {
      setLocalDownloading(version, false)
    }
  }

  function getDownloadProgress(version) {
    return Number(downloadProgressByVersion.value[version] || 0)
  }

  function backToStore() {
    router.push('/dashboard/store')
  }

  onMounted(() => {
    load()
  })

  return {
    appId,
    loading,
    error,
    actionError,
    actionMessage,
    appInfo,
    versions,
    actingByVersion,
    localDownloadingByVersion,
    getDownloadProgress,
    load,
    downloadAndInstallVersion,
    downloadPackageToLocal,
    backToStore,
    ...uploadModal,
  }
}

import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { resolveAppStoreBaseUrl, fetchOsConfig } from '../services/core/config'
import { downloadStorePackage, fetchStoreAppDetail } from '../services/core/store'
import { subscribeAppOperationEvents, uploadAppPackage } from '../services/core/apps'

export function useOnlineStoreDetailPage() {
  const { t } = useI18n()
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

  const downloadingByVersion = ref({})
  const installingByVersion = ref({})
  const downloadedFileByVersion = ref({})

  function setDownloading(version, busy) {
    downloadingByVersion.value = {
      ...downloadingByVersion.value,
      [version]: Boolean(busy),
    }
  }

  function setInstalling(version, busy) {
    installingByVersion.value = {
      ...installingByVersion.value,
      [version]: Boolean(busy),
    }
  }

  async function load() {
    loading.value = true
    error.value = ''
    actionError.value = ''
    actionMessage.value = ''
    try {
      const cfg = await fetchOsConfig()
      const baseUrl = resolveAppStoreBaseUrl(cfg?.data)
      storeBaseUrl.value = baseUrl

      const detail = await fetchStoreAppDetail(baseUrl, appId.value)
      appInfo.value = detail?.app || null
      versions.value = Array.isArray(detail?.versions)
        ? detail.versions.filter((item) => item?.status === 'published')
        : []
    } catch (err) {
      error.value = String(err?.message || err || t('store.loadFailed'))
    } finally {
      loading.value = false
    }
  }

  async function downloadVersion(version) {
    if (!version || downloadingByVersion.value[version]) return
    setDownloading(version, true)
    actionError.value = ''
    actionMessage.value = ''
    try {
      const result = await downloadStorePackage(storeBaseUrl.value, appId.value, version)
      downloadedFileByVersion.value = {
        ...downloadedFileByVersion.value,
        [version]: result.file,
      }
      actionMessage.value = t('store.downloadedReadyInstall', { version })
    } catch (err) {
      actionError.value = String(err?.message || err || t('store.downloadFailed'))
    } finally {
      setDownloading(version, false)
    }
  }

  function waitForOperation(operationId) {
    return new Promise((resolve, reject) => {
      let settled = false
      const subscription = subscribeAppOperationEvents(operationId, {
        onEvent(event) {
          if (!event || typeof event !== 'object') return
          if (event.type !== 'completed') return

          if (settled) return
          settled = true
          subscription.close()
          if (event.status === 'completed') {
            resolve(event.result || {})
          } else {
            reject(new Error(event.error || event.message || t('store.installFailed')))
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

  async function installVersion(version) {
    if (!version || installingByVersion.value[version]) return
    const file = downloadedFileByVersion.value[version]
    if (!file) {
      actionError.value = t('store.installNeedDownload')
      return
    }

    setInstalling(version, true)
    actionError.value = ''
    actionMessage.value = ''
    try {
      const operation = await uploadAppPackage(file)
      await waitForOperation(operation.operation_id)
      actionMessage.value = t('store.installSuccess', { version })
    } catch (err) {
      actionError.value = String(err?.message || err || t('store.installFailed'))
    } finally {
      setInstalling(version, false)
    }
  }

  function backToStore() {
    router.push('/dashboard/store')
  }

  function isVersionDownloaded(version) {
    return Boolean(downloadedFileByVersion.value[version])
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
    downloadingByVersion,
    installingByVersion,
    load,
    downloadVersion,
    installVersion,
    backToStore,
    isVersionDownloaded,
  }
}

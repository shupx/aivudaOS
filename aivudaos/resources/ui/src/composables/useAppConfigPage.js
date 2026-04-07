import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { fetchAppConfig, fetchAppVersions, updateAppConfig } from '../services/core/apps'

export function useAppConfigPage() {
  const { t } = useI18n()
  const route = useRoute()
  const router = useRouter()

  const loading = ref(false)
  const saving = ref(false)
  const error = ref('')
  const success = ref('')

  const versions = ref([])
  const selectedVersion = ref('')
  const configVersion = ref(0)
  const schemaText = ref('{}')
  const constraints = ref([])
  const configText = ref('{}')

  const appId = computed(() => String(route.params.appId || ''))

  async function loadVersions() {
    if (!appId.value) return
    const data = await fetchAppVersions(appId.value)
    versions.value = Array.isArray(data?.versions) ? data.versions : []
    if (!selectedVersion.value) {
      selectedVersion.value = data?.active_version || versions.value[0] || ''
    }
  }

  async function loadConfig() {
    if (!appId.value) return
    if (!selectedVersion.value) {
      error.value = t('appConfig.noVersion')
      return
    }

    loading.value = true
    error.value = ''
    success.value = ''
    try {
      const data = await fetchAppConfig(appId.value, selectedVersion.value)
      configVersion.value = Number(data?.version || 0)
      schemaText.value = JSON.stringify(data?.schema || {}, null, 2)
      constraints.value = Array.isArray(data?.constraints) ? data.constraints : []
      configText.value = JSON.stringify(data?.data || {}, null, 2)
      if (data?.app_version) {
        selectedVersion.value = String(data.app_version)
      }
    } catch (err) {
      error.value = String(err?.message || err || t('appConfig.loadFailed'))
    } finally {
      loading.value = false
    }
  }

  async function saveConfig() {
    if (!appId.value || !selectedVersion.value || saving.value) return
    error.value = ''
    success.value = ''

    let data
    try {
      data = JSON.parse(configText.value || '{}')
      if (typeof data !== 'object' || data === null || Array.isArray(data)) {
        throw new Error(t('appConfig.configMustObject'))
      }
    } catch (err) {
      error.value = String(err?.message || err || t('appConfig.invalidJson'))
      return
    }

    saving.value = true
    try {
      const resp = await updateAppConfig(appId.value, {
        version: configVersion.value,
        app_version: selectedVersion.value,
        data,
      })
      configVersion.value = Number(resp?.version || configVersion.value + 1)
      success.value = t('appConfig.saveSuccess')
    } catch (err) {
      error.value = String(err?.message || err || t('appConfig.saveFailed'))
    } finally {
      saving.value = false
    }
  }

  function goBack() {
    router.push(`/dashboard/apps/${encodeURIComponent(appId.value)}`)
  }

  watch(
    () => appId.value,
    async () => {
      selectedVersion.value = ''
      await loadVersions()
      await loadConfig()
    },
    { immediate: true },
  )

  watch(
    () => selectedVersion.value,
    async (next, prev) => {
      if (!next || next === prev) return
      await loadConfig()
    },
  )

  return {
    appId,
    loading,
    saving,
    error,
    success,
    versions,
    selectedVersion,
    configVersion,
    schemaText,
    constraints,
    configText,
    loadConfig,
    saveConfig,
    goBack,
  }
}

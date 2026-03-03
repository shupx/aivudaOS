import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  fetchOsConfig,
  resolveAppStoreBaseUrl,
  saveAppStoreBaseUrl,
} from '../services/core/config'
import { fetchStoreIndex, normalizeStoreBaseUrl } from '../services/core/store'
import { useStoreDisplayFormat } from './useStoreDisplayFormat'

export function useOnlineStorePage() {
  const { t } = useI18n()
  const { formatStoreUpdatedAt } = useStoreDisplayFormat()

  const loading = ref(false)
  const savingAddress = ref(false)
  const error = ref('')
  const addressError = ref('')
  const storeAddress = ref('')
  const items = ref([])

  const hasItems = computed(() => items.value.length > 0)
  const displayItems = computed(() => (
    items.value.map((item) => ({
      ...item,
      updated_at_display: formatStoreUpdatedAt(item?.updated_at),
    }))
  ))

  async function load() {
    loading.value = true
    error.value = ''
    try {
      const cfg = await fetchOsConfig()
      const baseUrl = resolveAppStoreBaseUrl(cfg?.data)
      storeAddress.value = baseUrl
      const data = await fetchStoreIndex(baseUrl)
      items.value = Array.isArray(data?.items) ? data.items : []
    } catch (err) {
      error.value = String(err?.message || err || t('store.loadFailed'))
    } finally {
      loading.value = false
    }
  }

  async function saveAddress() {
    if (savingAddress.value) return
    savingAddress.value = true
    addressError.value = ''
    error.value = ''
    try {
      const cleanUrl = normalizeStoreBaseUrl(storeAddress.value)
      if (!/^https?:\/\//.test(cleanUrl)) {
        throw new Error(t('store.invalidAddress'))
      }
      const saved = await saveAppStoreBaseUrl(cleanUrl)
      storeAddress.value = saved
      const data = await fetchStoreIndex(saved)
      items.value = Array.isArray(data?.items) ? data.items : []
    } catch (err) {
      addressError.value = String(err?.message || err || t('store.saveAddressFailed'))
    } finally {
      savingAddress.value = false
    }
  }

  onMounted(() => {
    load()
  })

  return {
    loading,
    savingAddress,
    error,
    addressError,
    storeAddress,
    items,
    displayItems,
    hasItems,
    load,
    saveAddress,
  }
}

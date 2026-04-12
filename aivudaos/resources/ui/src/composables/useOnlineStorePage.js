import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
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
  const searchText = ref('')
  const items = ref([])

  const hasItems = computed(() => items.value.length > 0)
  const normalizedStoreAddress = computed(() => normalizeStoreBaseUrl(storeAddress.value))
  const canOpenStoreAddress = computed(() => /^https?:\/\//.test(normalizedStoreAddress.value))
  const showAddressManualCheckHint = computed(() => (
    Boolean(addressError.value || error.value) && canOpenStoreAddress.value
  ))
  const displayItems = computed(() => (
    items.value
      .map((item) => ({
        ...item,
        updated_at_display: formatStoreUpdatedAt(item?.updated_at),
      }))
      .filter((item) => matchesSearch(item, searchText.value))
  ))

  async function load() {
    loading.value = true
    error.value = ''
    try {
      const baseUrl = resolveAppStoreBaseUrl()
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
    searchText,
    normalizedStoreAddress,
    canOpenStoreAddress,
    showAddressManualCheckHint,
    items,
    displayItems,
    hasItems,
    load,
    saveAddress,
  }
}

function matchesSearch(item, rawSearchText) {
  const keyword = String(rawSearchText || '').trim().toLowerCase()
  if (!keyword) return true
  const appName = String(item?.manifest?.name || item?.app_id || '').toLowerCase()
  return appName.includes(keyword)
}

import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  resolveAppStoreBaseUrl,
  saveAppStoreBaseUrl,
} from '../services/core/config'
import {
  buildStoreCaddyLocalCaDownloadUrl,
  fetchStoreIndex,
  normalizeStoreBaseUrl,
} from '../services/core/store'
import { useStoreDisplayFormat } from './useStoreDisplayFormat'

const STORE_SORT_OPTION_STORAGE_KEY = 'ONLINE_STORE_SORT_OPTION'
const STORE_SORT_DESC_STORAGE_KEY = 'ONLINE_STORE_SORT_DESC'

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
  const addressCertificateHintVisible = ref(false)
  const storedSortOption = localStorage.getItem(STORE_SORT_OPTION_STORAGE_KEY) || 'updated_at'
  const storedSortDesc = localStorage.getItem(STORE_SORT_DESC_STORAGE_KEY)
  const sortOption = ref(storedSortOption)
  const sortDesc = ref(storedSortDesc === null ? storedSortOption === 'updated_at' : storedSortDesc === '1')

  const hasItems = computed(() => items.value.length > 0)
  const normalizedStoreAddress = computed(() => normalizeStoreBaseUrl(storeAddress.value))
  const canOpenStoreAddress = computed(() => /^https?:\/\//.test(normalizedStoreAddress.value))
  const storeCertificateDownloadUrl = computed(() => (
    canOpenStoreAddress.value
      ? buildStoreCaddyLocalCaDownloadUrl(normalizedStoreAddress.value)
      : ''
  ))
  const showAddressManualCheckHint = computed(() => canOpenStoreAddress.value)
  const displayItems = computed(() => (
    items.value
      .map((item) => ({
        ...item,
        updated_at_display: formatStoreUpdatedAt(item?.updated_at),
      }))
      .filter((item) => matchesSearch(item, searchText.value))
      .sort((left, right) => compareStoreItems(left, right, sortOption.value, sortDesc.value))
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
    addressCertificateHintVisible.value = false
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

  function openStoreCertificate() {
    if (!storeCertificateDownloadUrl.value || loading.value || savingAddress.value) return

    addressCertificateHintVisible.value = true
    error.value = ''
  }

  function setSortOption(nextOption) {
    const normalized = nextOption === 'name' ? 'name' : 'updated_at'
    if (sortOption.value === normalized) {
      toggleSortDesc()
      return
    }
    sortOption.value = normalized
    sortDesc.value = normalized === 'updated_at'
    localStorage.setItem(STORE_SORT_OPTION_STORAGE_KEY, normalized)
    localStorage.setItem(STORE_SORT_DESC_STORAGE_KEY, sortDesc.value ? '1' : '0')
  }

  function toggleSortDesc() {
    sortDesc.value = !sortDesc.value
    localStorage.setItem(STORE_SORT_DESC_STORAGE_KEY, sortDesc.value ? '1' : '0')
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
    storeCertificateDownloadUrl,
    showAddressManualCheckHint,
    addressCertificateHintVisible,
    items,
    sortOption,
    sortDesc,
    displayItems,
    hasItems,
    load,
    saveAddress,
    openStoreCertificate,
    setSortOption,
    toggleSortDesc,
  }
}

function matchesSearch(item, rawSearchText) {
  const keyword = String(rawSearchText || '').trim().toLowerCase()
  if (!keyword) return true
  const appName = String(item?.manifest?.name || item?.app_id || '').toLowerCase()
  return appName.includes(keyword)
}

function compareStoreItems(left, right, sortOption, sortDesc) {
  const direction = sortDesc ? -1 : 1

  if (sortOption === 'name') {
    return getStoreItemName(left).localeCompare(getStoreItemName(right)) * direction
  }

  const leftUpdatedAt = parseStoreUpdatedAt(left?.updated_at)
  const rightUpdatedAt = parseStoreUpdatedAt(right?.updated_at)
  if (leftUpdatedAt !== rightUpdatedAt) {
    return (leftUpdatedAt - rightUpdatedAt) * direction
  }

  return getStoreItemName(left).localeCompare(getStoreItemName(right))
}

function getStoreItemName(item) {
  return String(item?.manifest?.name || item?.app_id || '')
}

function parseStoreUpdatedAt(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  const stamp = Date.parse(String(value || ''))
  return Number.isFinite(stamp) ? stamp : 0
}

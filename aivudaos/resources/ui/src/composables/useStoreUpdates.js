import { computed } from 'vue'
import { appState, setApps } from '../state/appState'
import { fetchInstalledApps } from '../services/core/apps'
import { resolveAppStoreBaseUrl } from '../services/core/config'
import { fetchStoreIndex } from '../services/core/store'
import { annotateStoreItems } from '../services/core/storeUpdates'

export function useStoreUpdates() {
  const storeItems = computed(() => annotateStoreItems(appState.storeItems, appState.apps))
  const updateCount = computed(() => new Set(storeItems.value
    .filter((item) => item.installation_status === 'updateAvailable')
    .map((item) => item.app_id)).size)

  async function refreshInstalledApps() {
    setApps(await fetchInstalledApps())
  }

  async function refreshStoreIndex(baseUrl = resolveAppStoreBaseUrl()) {
    // Hide results from a previous address immediately; failed requests cannot
    // leave another store's update count visible.
    if (appState.storeBaseUrl !== baseUrl) {
      appState.storeBaseUrl = baseUrl
      appState.storeItems = []
    }
    try {
      const data = await fetchStoreIndex(baseUrl)
      if (appState.storeBaseUrl === baseUrl) {
        appState.storeItems = Array.isArray(data?.items) ? data.items : []
      }
    } catch (error) {
      if (appState.storeBaseUrl === baseUrl) appState.storeItems = []
      throw error
    }
  }

  return { storeItems, updateCount, refreshStoreIndex, refreshInstalledApps }
}

import { computed, onMounted } from 'vue'
import { refreshInstalledApps } from '../state/installedApps'
import { appState, runningAppCount } from '../state/appState'
import { fetchAivudaosServiceStatus } from '../services/core/config'

let versionLoadPromise = null

async function ensureAivudaosVersionLoaded() {
  if (!appState.token || appState.aivudaosVersion) return
  if (!versionLoadPromise) {
    versionLoadPromise = fetchAivudaosServiceStatus()
      .then((data) => {
        appState.aivudaosVersion = String(data?.version || '')
      })
      .catch(() => {})
      .finally(() => {
        versionLoadPromise = null
      })
  }
  await versionLoadPromise
}

export function useSystemStatus() {
  void ensureAivudaosVersionLoaded()
  onMounted(refreshInstalledApps)

  const user = computed(() => appState.user)
  const role = computed(() => appState.role)
  const aivudaosVersion = computed(() => appState.aivudaosVersion)
  const gatewayOnline = computed(() => appState.gatewayOnline)
  const totalApps = computed(() => appState.apps.length)
  const autostartApps = computed(() => appState.apps.filter((item) => Boolean(item.autostart)).length)
  const lastSyncAt = computed(() => appState.lastSyncAt)

  return {
    user,
    role,
    aivudaosVersion,
    gatewayOnline,
    totalApps,
    runningApps: runningAppCount,
    autostartApps,
    lastSyncAt,
  }
}
